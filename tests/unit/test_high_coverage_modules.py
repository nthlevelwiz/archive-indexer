import json
from pathlib import Path

import pytest

from archive_indexer.adapters import db as db_mod
from archive_indexer.adapters.embedding import cosine_similarity, embed_text
from archive_indexer.adapters.ocr import extract_frame_ocr_text
from archive_indexer.app import cli
from archive_indexer.services import ingest_service


def test_embedding_and_ocr_basics():
    emb = embed_text("hello", dimensions=8)
    assert len(emb) == 8
    assert pytest.approx(sum(v * v for v in emb), rel=1e-6) == 1.0
    assert cosine_similarity([1.0, 0.0], [1.0, 1.0]) == 1.0
    assert extract_frame_ocr_text("/tmp/my-video_file.mp4", second=9) == "frame 9s text from my video file"


def _new_db(tmp_path: Path):
    db_path = tmp_path / "db" / "archive_index.sqlite"
    db_mod.init_db(db_path)
    return db_path


def test_db_adapters_end_to_end(tmp_path: Path):
    db_path = _new_db(tmp_path)
    conn = db_mod.connect_db(db_path)
    try:
        db_mod.upsert_source(conn, "s1", "/tmp", "lbl", "{}")
        db_mod.upsert_item(conn, ("i1", "s1", "file", "/tmp/a.txt", "a.txt", ".txt", "text/plain", 1, "m", "h", "{}", db_mod.now_iso()))
        db_mod.upsert_chunk(conn, ("c1", "i1", "path_metadata", "hello", "{}", db_mod.now_iso()))
        db_mod.insert_fts(conn, "c1", "hello")
        db_mod.upsert_bucket_definition(conn, "b", "desc", "manual")
        db_mod.insert_bucket_rule(conn, "r1", "b", "contains", "hello", 0.5, "chunk")
        db_mod.upsert_item_bucket(conn, "i1", "b", 0.8, json.dumps({"x": 1}), "unit", db_mod.now_iso())
        db_mod.upsert_bookmark_source(conn, "bm", "/tmp/bm.html", "bm", "{}")
        conn.commit()

        assert db_mod.get_item_row_by_path(conn, "/tmp/a.txt")["id"] == "i1"
        assert db_mod.get_chunk_by_item_and_type(conn, "i1", "path_metadata")["id"] == "c1"
    finally:
        conn.close()


def test_ingest_folders_and_bookmarks_and_cli_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)

    root = tmp_path / "srcfiles"
    (root / "nested").mkdir(parents=True)
    (root / "nested" / "a.mp3").write_bytes(b"a")
    (root / "b.mp4").write_bytes(b"b")
    (root / "c.txt").write_text("c", encoding="utf-8")

    (config_dir / "buckets.yaml").write_text("buckets: []\n", encoding="utf-8")

    (config_dir / "sources.yaml").write_text(
        f"sources:\n  - type: folder\n    label: docs\n    path: {root}\n  - type: other\n    label: skip\n    path: /tmp\n",
        encoding="utf-8",
    )

    db_path = data_dir / "archive_index.sqlite"
    assert cli.main(["--data-dir", str(data_dir), "init-db"]) == 0
    assert cli.main(["--data-dir", str(data_dir), "--config-dir", str(config_dir), "ingest", "--source", "docs"]) == 0
    out = capsys.readouterr().out
    assert "ingested" in out

    # second ingest should skip unchanged files
    inserted_second = ingest_service.ingest_folders(db_path, config_dir, "docs")
    assert inserted_second == 0

    bm = tmp_path / "bookmarks.html"
    bm.write_text('<DL><p><DT><H3>F</H3><DL><p><DT><A HREF="https://example.com">Ex</A>', encoding="utf-8")
    assert cli.main(["--data-dir", str(data_dir), "ingest-bookmarks", str(bm)]) == 0

    assert cli.main(["--data-dir", str(data_dir), "embed"]) == 0
    assert cli.main(["--data-dir", str(data_dir), "ocr-videos"]) == 0
    assert cli.main(["--data-dir", str(data_dir), "--config-dir", str(config_dir), "assign-buckets"]) == 0

    conn = db_mod.connect_db(db_path)
    try:
        first = conn.execute("SELECT path_or_url FROM items LIMIT 1").fetchone()["path_or_url"]
        assert cli.main(["--data-dir", str(data_dir), "show-item", first]) == 0
        assert cli.main(["--data-dir", str(data_dir), "explain-buckets", first]) == 0
        assert cli.main(["--data-dir", str(data_dir), "list-bucket", "does-not-exist"]) == 0
        assert cli.main(["--data-dir", str(data_dir), "bucket-stats"]) == 0

        assert cli.main(["--data-dir", str(data_dir), "search", "frame"]) == 0
        assert cli.main(["--data-dir", str(data_dir), "search", "frame", "--bucket", "does-not-exist"]) == 0
    finally:
        conn.close()

    # unknown command path prints help
    assert cli.main(["--data-dir", str(data_dir)]) == 0
