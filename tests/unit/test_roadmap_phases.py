print("running tests/unit/test_roadmap_phases.py")
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def run(cmd, cwd):
    print(f"executing command: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=cwd, env=ENV, check=True, capture_output=True, text=True)


def test_roadmap_phases_end_to_end(tmp_path: Path):
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

    run(["python", "-m", "archive_indexer", "--data-dir", "data", "--config-dir", "config", "init-db"], tmp_path)
    run(["python", "-m", "archive_indexer", "--data-dir", "data", "--config-dir", "config", "ingest"], tmp_path)
    run(["python", "-m", "archive_indexer", "--data-dir", "data", "ingest-bookmarks", str(bookmarks)], tmp_path)
    run(["python", "-m", "archive_indexer", "--data-dir", "data", "--config-dir", "config", "assign-buckets"], tmp_path)
    run(["python", "-m", "archive_indexer", "--data-dir", "data", "embed"], tmp_path)
    run(["python", "-m", "archive_indexer", "--data-dir", "data", "ocr-videos"], tmp_path)
    result = run(["python", "-m", "archive_indexer", "--data-dir", "data", "search", "electric"], tmp_path)
    assert "electric" in result.stdout.lower()

    db = tmp_path / "data" / "archive_index.kuzu"
    from archive_indexer.adapters.db import connect_db

    conn = connect_db(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] >= 4
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] >= 4
        assert conn.execute("SELECT COUNT(*) FROM item_buckets").fetchone()[0] >= 1
        assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] >= 1
        assert conn.execute("SELECT COUNT(*) FROM chunks WHERE chunk_type='frame_ocr'").fetchone()[0] >= 1
    finally:
        conn.close()
