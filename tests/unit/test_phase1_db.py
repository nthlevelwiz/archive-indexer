print("running tests/unit/test_phase1_db.py")
import os
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}

EXPECTED_TABLES = {
    "sources",
    "items",
    "chunks",
    "bucket_definitions",
    "bucket_rules",
    "item_buckets",
    "embeddings",
    "schema_version",
    "chunk_fts",
}


def test_init_db_creates_database_and_schema(tmp_path: Path):
    data_dir = tmp_path / "data"
    print("executing command")
    subprocess.run(
        ["python", "-m", "archive_indexer", "--data-dir", str(data_dir), "init-db"],
        check=True,
        env=ENV,
    )

    db_path = data_dir / "archive_index.sqlite"
    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
        names = {r[0] for r in rows}
        assert EXPECTED_TABLES.issubset(names)

        fts_row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='chunk_fts'"
        ).fetchone()
        assert fts_row is not None

        conn.execute("INSERT INTO chunk_fts(chunk_id, text) VALUES (?, ?)", ("c1", "hello"))
        matched = conn.execute(
            "SELECT chunk_id FROM chunk_fts WHERE chunk_fts MATCH 'hello'"
        ).fetchone()
        assert matched[0] == "c1"
    finally:
        conn.close()
