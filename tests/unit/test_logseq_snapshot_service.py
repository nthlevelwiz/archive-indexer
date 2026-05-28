import json
from pathlib import Path

from archive_indexer.adapters.db import connect_db, init_db
from archive_indexer.services.bucket_service import assign_buckets
from archive_indexer.services.ingest_service import ingest_folders
from archive_indexer.services.logseq_snapshot_service import build_logseq_snapshot, write_logseq_snapshot


def test_logseq_snapshot_exports_existing_tables_without_embeddings(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    archive = tmp_path / "archive"
    config_dir.mkdir(parents=True)
    archive.mkdir(parents=True)
    (archive / "electric notes.txt").write_text("electric panel checklist", encoding="utf-8")
    (config_dir / "sources.yaml").write_text(
        f"sources:\n  - type: folder\n    label: local\n    path: {archive}\n",
        encoding="utf-8",
    )
    (config_dir / "buckets.yaml").write_text(
        "buckets:\n"
        "  - name: electrical\n"
        "    threshold: 1\n"
        "    rules:\n"
        "      - type: text_regex\n"
        "        pattern: electric\n"
        "        weight: 1\n",
        encoding="utf-8",
    )

    db_path = data_dir / "archive_index.sqlite"
    init_db(db_path)
    assert ingest_folders(db_path, config_dir, "local") == 1
    assert assign_buckets(db_path, config_dir) >= 1
    conn = connect_db(db_path)
    try:
        chunk_id = conn.execute("SELECT id FROM chunks LIMIT 1").fetchone()["id"]
        conn.execute(
            "INSERT INTO embeddings(id, chunk_id, model, embedding_json, dimensions, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            ("emb1", chunk_id, "unit-model", "[0.1, 0.2]", 2),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr("archive_indexer.adapters.db._default_data_dir", data_dir)
    snapshot = build_logseq_snapshot()

    assert snapshot["format"] == "archive-indexer-logseq-snapshot"
    assert snapshot["direction"] == "archive-indexer-to-logseq"
    assert snapshot["read_only_source"] is True
    assert snapshot["items"][0]["chunks"][0]["text"]
    assert snapshot["items"][0]["buckets"][0]["bucket_name"] == "electrical"
    assert snapshot["embedding_stats"] == [{"model": "unit-model", "count": 1, "dimensions": 2}]
    assert "embedding_json" not in json.dumps(snapshot)

    output_path = write_logseq_snapshot(tmp_path / "snapshot" / "archive.json")
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded["items"][0]["path_or_url"].endswith("electric notes.txt")
