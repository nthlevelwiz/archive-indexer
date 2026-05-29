from pathlib import Path

from archive_indexer.adapters.db import init_db, connect_db
from archive_indexer.services.bucket_service import assign_buckets


def test_assign_buckets_assigns_match_and_fallback(tmp_path: Path):
    db_path = tmp_path / "data" / "archive_graph.json"
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "buckets.yaml").write_text(
        "buckets:\n  - name: electrical\n    threshold: 1\n    rules:\n      - type: text_regex\n        pattern: electric\n        weight: 1\n"
    )

    init_db(db_path)
    conn = connect_db(db_path)
    conn.execute("INSERT INTO items(id, source_id, item_type, path_or_url, filename, extension, indexed_at) VALUES ('1','s','file','/x/electric.txt','electric.txt','.txt','now')")
    conn.execute("INSERT INTO items(id, source_id, item_type, path_or_url, filename, extension, indexed_at) VALUES ('2','s','file','/x/other.txt','other.txt','.txt','now')")
    conn.commit(); conn.close()

    count = assign_buckets(db_path, cfg_dir)
    assert count == 2

    conn = connect_db(db_path)
    rows = conn.execute("SELECT item_id,bucket_name FROM item_buckets ORDER BY item_id").fetchall()
    conn.close()
    assert [(r["item_id"], r["bucket_name"]) for r in rows] == [("1", "electrical"), ("2", "review_later")]
