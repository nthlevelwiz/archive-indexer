print("running tests/unit/test_phase1_db.py")
import os
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
    assert db_path.read_text(encoding="utf-8")
