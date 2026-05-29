print("running tests/unit/test_phase2_ingest.py")
from pathlib import Path

import pytest

from archive_indexer.services import ingest_service
from mock_db import MockGraphAdapter


def test_phase2_ingest_folder_and_reingest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mock_db = MockGraphAdapter()
    monkeypatch.setattr(ingest_service, "connect_db", lambda db_path=None: mock_db)

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

    inserted = ingest_service.ingest_folders(None, cfg_dir, "local")
    assert inserted == 2

    inserted_second = ingest_service.ingest_folders(None, cfg_dir, "local")
    assert inserted_second == 0

    items = mock_db.execute("SELECT path_or_url, item_type FROM items ORDER BY path_or_url").fetchall()
    assert len(items) == 2
    assert all(".hidden" not in row[0] for row in items)

    chunk_types = [r[0] for r in mock_db.execute("SELECT chunk_type FROM chunks").fetchall()]
    assert "path_metadata" in chunk_types
    assert "audio_metadata" in chunk_types
