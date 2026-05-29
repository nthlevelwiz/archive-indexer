print("running tests/unit/test_roadmap_phases.py")
from pathlib import Path

import pytest

from archive_indexer.adapters.embedding import embed_text
from archive_indexer.adapters.ocr import extract_frame_ocr_text
from archive_indexer.app import cli
from archive_indexer.services import bucket_service, ingest_service
from mock_db import MockGraphAdapter


def test_roadmap_phases_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    mock_db = MockGraphAdapter()
    monkeypatch.setattr(cli, "init_db", mock_db.init_schema)
    monkeypatch.setattr(cli, "DatabaseAdapter", lambda: mock_db)
    monkeypatch.setattr(ingest_service, "connect_db", lambda db_path=None: mock_db)
    monkeypatch.setattr(bucket_service, "connect_db", lambda db_path=None: mock_db)

    (tmp_path / "config").mkdir(); (tmp_path / "data").mkdir(); (tmp_path / "archive").mkdir()
    media = tmp_path / "archive" / "videos"
    media.mkdir(parents=True)
    (media / "clip.mp4").write_text("video bytes")
    (tmp_path / "archive" / "audio.wav").write_text("audio bytes")
    (tmp_path / "archive" / "note.txt").write_text("electrician apprenticeship notes")

    (tmp_path / "config" / "sources.yaml").write_text(
        f"sources:\n  - label: Local\n    type: folder\n    path: {tmp_path / 'archive'}\n"
    )
    (tmp_path / "config" / "buckets.yaml").write_text("buckets:\n  - name: electrical\n")
    bookmarks = tmp_path / "bookmarks.html"
    bookmarks.write_text('<DL><DT><H3>Tech</H3><DL><DT><A HREF="https://example.com/electric">Electrical</A></DL></DL>')

    assert cli.main(["--data-dir", str(tmp_path / "data"), "--config-dir", str(tmp_path / "config"), "init-db"]) == 0
    assert cli.main(["--data-dir", str(tmp_path / "data"), "--config-dir", str(tmp_path / "config"), "ingest"]) == 0
    assert cli.main(["--data-dir", str(tmp_path / "data"), "ingest-bookmarks", str(bookmarks)]) == 0
    assert cli.main(["--data-dir", str(tmp_path / "data"), "--config-dir", str(tmp_path / "config"), "assign-buckets"]) == 0
    assert cli.main(["--data-dir", str(tmp_path / "data"), "embed"]) == 0
    assert cli.main(["--data-dir", str(tmp_path / "data"), "ocr-videos"]) == 0
    assert cli.main(["--data-dir", str(tmp_path / "data"), "search", "electric"]) == 0
    result = capsys.readouterr()
    assert "electric" in result.out.lower()

    assert mock_db.execute("SELECT COUNT(*) FROM items").fetchone()[0] >= 4
    assert mock_db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] >= 4
    assert mock_db.execute("SELECT COUNT(*) FROM item_buckets").fetchone()[0] >= 1
    assert mock_db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] >= 1
    assert mock_db.execute("SELECT COUNT(*) FROM chunks WHERE chunk_type='frame_ocr'").fetchone()[0] >= 1
