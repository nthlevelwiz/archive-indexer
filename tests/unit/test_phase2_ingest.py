print("running tests/unit/test_phase2_ingest.py")
from pathlib import Path

from archive_indexer.adapters.db import connect_db, init_db
from archive_indexer.services.ingest_service import ingest_folders


def test_phase2_ingest_folder_and_reingest(tmp_path: Path):
    data_dir = tmp_path / "data"
    cfg_dir = tmp_path / "config"
    archive = tmp_path / "archive"
    cfg_dir.mkdir(parents=True)
    archive.mkdir(parents=True)

    (archive / "note.txt").write_text("hello", encoding="utf-8")
    (archive / "song.mp3").write_bytes(b"abc")
    (archive / ".hidden").mkdir()
    (archive / ".hidden" / "skip.txt").write_text("hidden", encoding="utf-8")

    (cfg_dir / "sources.yaml").write_text(
        f"sources:\n  - type: folder\n    label: local\n    path: {archive}\n",
        encoding="utf-8",
    )

    db_path = data_dir / "archive_graph.json"
    init_db(db_path)

    inserted = ingest_folders(db_path, cfg_dir, "local")
    assert inserted == 2

    inserted_second = ingest_folders(db_path, cfg_dir, "local")
    assert inserted_second == 0

    conn = connect_db(db_path)
    try:
        items = conn.execute("SELECT path_or_url, item_type FROM items ORDER BY path_or_url").fetchall()
        assert len(items) == 2
        assert all(".hidden" not in row[0] for row in items)

        chunk_types = [r[0] for r in conn.execute("SELECT chunk_type FROM chunks").fetchall()]
        assert "path_metadata" in chunk_types
        assert "audio_metadata" in chunk_types
    finally:
        conn.close()
