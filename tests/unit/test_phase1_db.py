print("running tests/unit/test_phase1_db.py")
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def test_init_db_creates_database_and_schema(tmp_path: Path):
    data_dir = tmp_path / "data"
    print("executing command")
    result = subprocess.run(
        ["python", "-m", "archive_indexer", "--data-dir", str(data_dir), "init-db"],
        check=True,
        capture_output=True,
        text=True,
        env=ENV,
    )

    assert "Using fallback file-backed graph database" in result.stderr
    assert str(data_dir / "archive_graph.json") in result.stderr

    db_path = data_dir / "archive_graph.json"
    assert db_path.exists()
    assert db_path.read_text(encoding="utf-8")


def test_init_db_ignores_legacy_sqlite_file_in_data_dir(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    legacy_sqlite = data_dir / "archive_index.sqlite"
    legacy_sqlite.write_bytes(b"SQLite format 3\x00\x8dlegacy")

    subprocess.run(
        ["python", "-m", "archive_indexer", "--data-dir", str(data_dir), "init-db"],
        check=True,
        env=ENV,
    )

    assert legacy_sqlite.read_bytes().startswith(b"SQLite format 3")
    assert (data_dir / "archive_graph.json").exists()
