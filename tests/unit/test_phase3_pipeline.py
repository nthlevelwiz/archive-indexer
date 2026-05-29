print("running tests/unit/test_phase3_pipeline.py")
from pathlib import Path

import pytest

from archive_indexer.services import bucket_service, ingest_service
from mock_db import MockGraphAdapter


def test_phase3_bucket_assignment_and_bookmark_ingest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mock_db = MockGraphAdapter()
    monkeypatch.setattr(ingest_service, "connect_db", lambda db_path=None: mock_db)
    monkeypatch.setattr(bucket_service, "connect_db", lambda db_path=None: mock_db)

    cfg_dir = tmp_path / "config"
    archive = tmp_path / "archive"
    cfg_dir.mkdir(parents=True)
    archive.mkdir(parents=True)

    (archive / "electric_notes.txt").write_text("electric panel checklist", encoding="utf-8")
    (archive / "other.txt").write_text("random", encoding="utf-8")

    (cfg_dir / "sources.yaml").write_text(
        f"sources:\n  - type: folder\n    label: local\n    path: {archive}\n",
        encoding="utf-8",
    )
    (cfg_dir / "buckets.yaml").write_text(
        "buckets:\n"
        "  - name: electrical\n"
        "    threshold: 1\n"
        "    rules:\n"
        "      - type: text_regex\n"
        "        pattern: electric\n"
        "        weight: 1\n",
        encoding="utf-8",
    )

    bm = tmp_path / "bookmarks.html"
    bm.write_text('<DL><DT><H3>Tech</H3><DL><DT><A HREF="https://example.com/electric">Electrical</A></DL></DL>', encoding="utf-8")

    assert ingest_service.ingest_folders(None, cfg_dir, "local") == 2
    assert ingest_service.ingest_bookmarks(None, bm) == 1

    assigned = bucket_service.assign_buckets(None, cfg_dir)
    assert assigned >= 3

    rows = mock_db.execute("SELECT bucket_name, COUNT(*) FROM item_buckets GROUP BY bucket_name").fetchall()
    names = {r[0] for r in rows}
    assert "electrical" in names
    assert "review_later" in names
