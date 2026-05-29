from pathlib import Path

import pytest

from archive_indexer.services import bucket_service
from mock_db import MockGraphAdapter


def test_assign_buckets_assigns_match_and_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mock_db = MockGraphAdapter()
    monkeypatch.setattr(bucket_service, "connect_db", lambda db_path=None: mock_db)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "buckets.yaml").write_text(
        "buckets:\n  - name: electrical\n    threshold: 1\n    rules:\n      - type: text_regex\n        pattern: electric\n        weight: 1\n"
    )

    mock_db.execute("INSERT INTO items(id, source_id, item_type, path_or_url, filename, extension, indexed_at) VALUES ('1','s','file','/x/electric.txt','electric.txt','.txt','now')")
    mock_db.execute("INSERT INTO items(id, source_id, item_type, path_or_url, filename, extension, indexed_at) VALUES ('2','s','file','/x/other.txt','other.txt','.txt','now')")

    count = bucket_service.assign_buckets(None, cfg_dir)
    assert count == 2

    rows = mock_db.execute("SELECT item_id,bucket_name FROM item_buckets ORDER BY item_id").fetchall()
    assert [(r["item_id"], r["bucket_name"]) for r in rows] == [("1", "electrical"), ("2", "review_later")]
