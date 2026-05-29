print("running tests/unit/test_phase1_db.py")
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}

EXPECTED_TABLES = {
    "Source",
    "Item",
    "Chunk",
    "BucketDefinition",
    "BucketRule",
    "ItemBucket",
    "Embedding",
    "SchemaVersion",
    "ChunkFts",
}


def test_init_db_creates_database_and_schema(tmp_path: Path):
    data_dir = tmp_path / "data"
    print("executing command")
    subprocess.run(
        ["python", "-m", "archive_indexer", "--data-dir", str(data_dir), "init-db"],
        check=True,
        env=ENV,
    )

    db_path = data_dir / "archive_index.kuzu"
    assert db_path.exists()

    from archive_indexer.adapters.db import DatabaseAdapter, connect_db

    conn = connect_db(db_path)
    try:
        adapter = DatabaseAdapter(conn)
        adapter.upsert_item(("i1", "s1", "file", "/tmp/hello.txt", "hello.txt", ".txt", "text/plain", 5, "m", "h", "{}", "now"))
        adapter.upsert_chunk(("c1", "i1", "path_metadata", "hello", "{}", "now"))
        adapter.insert_fts("c1", "hello")
        conn.commit()

        assert db_path.exists()
        assert EXPECTED_TABLES
        matched = adapter.search_chunks("hello")
        assert matched[0]["text"] == "hello"
    finally:
        conn.close()
