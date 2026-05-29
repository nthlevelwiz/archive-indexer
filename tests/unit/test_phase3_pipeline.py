print("running tests/unit/test_phase3_pipeline.py")
from pathlib import Path

from archive_indexer.adapters.db import connect_db, init_db
from archive_indexer.services.bucket_service import assign_buckets
from archive_indexer.services.ingest_service import ingest_bookmarks, ingest_folders


def test_phase3_bucket_assignment_and_bookmark_ingest(tmp_path: Path):
    data_dir = tmp_path / "data"
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

    db_path = data_dir / "archive_index.kuzu"
    init_db(db_path)
    assert ingest_folders(db_path, cfg_dir, "local") == 2
    assert ingest_bookmarks(db_path, bm) == 1

    assigned = assign_buckets(db_path, cfg_dir)
    assert assigned >= 3

    conn = connect_db(db_path)
    try:
        rows = conn.execute("SELECT bucket_name, COUNT(*) FROM item_buckets GROUP BY bucket_name").fetchall()
        names = {r[0] for r in rows}
        assert "electrical" in names
        assert "review_later" in names
    finally:
        conn.close()
