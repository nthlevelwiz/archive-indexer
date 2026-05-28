from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..adapters.db import DatabaseAdapter, now_iso

SNAPSHOT_FORMAT_VERSION = 1


def _rows_to_dicts(rows) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _decode_jsonish(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def build_logseq_snapshot() -> dict[str, Any]:
    """Build a read-only JSON snapshot for the Logseq plugin.

    The snapshot is intentionally derived from existing Archive Indexer tables. It
    does not introduce Logseq-specific tables and it excludes embedding vectors so
    the plugin can browse archive metadata without copying large vector payloads.
    """
    db = DatabaseAdapter()
    try:
        sources = _rows_to_dicts(db.conn.execute("SELECT * FROM sources ORDER BY label, id").fetchall())
        items = _rows_to_dicts(db.conn.execute("SELECT * FROM items ORDER BY indexed_at DESC, path_or_url").fetchall())
        chunks = _rows_to_dicts(
            db.conn.execute(
                """
                SELECT id, item_id, chunk_type, text, timestamp_start, timestamp_end, metadata_json, created_at
                FROM chunks
                ORDER BY created_at, id
                """
            ).fetchall()
        )
        item_buckets = _rows_to_dicts(
            db.conn.execute(
                """
                SELECT item_id, bucket_name, confidence, evidence_json, assigned_by, assigned_at
                FROM item_buckets
                ORDER BY bucket_name, item_id
                """
            ).fetchall()
        )
        bucket_definitions = _rows_to_dicts(db.conn.execute("SELECT * FROM bucket_definitions ORDER BY name").fetchall())
        bucket_stats = _rows_to_dicts(db.fetch_bucket_stats())
        embedding_stats = _rows_to_dicts(
            db.conn.execute(
                "SELECT model, COUNT(*) AS count, MAX(dimensions) AS dimensions FROM embeddings GROUP BY model ORDER BY model"
            ).fetchall()
        )
    finally:
        db.close()

    for source in sources:
        source["config"] = _decode_jsonish(source.pop("config_json", None))
    for item in items:
        item["metadata"] = _decode_jsonish(item.pop("metadata_json", None))
    for chunk in chunks:
        chunk["metadata"] = _decode_jsonish(chunk.pop("metadata_json", None))
    for bucket in item_buckets:
        bucket["evidence"] = _decode_jsonish(bucket.pop("evidence_json", None))

    chunks_by_item: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        chunks_by_item.setdefault(chunk["item_id"], []).append(chunk)

    buckets_by_item: dict[str, list[dict[str, Any]]] = {}
    for bucket in item_buckets:
        buckets_by_item.setdefault(bucket["item_id"], []).append(bucket)

    for item in items:
        item["chunks"] = chunks_by_item.get(item["id"], [])
        item["buckets"] = buckets_by_item.get(item["id"], [])

    return {
        "format": "archive-indexer-logseq-snapshot",
        "format_version": SNAPSHOT_FORMAT_VERSION,
        "generated_at": now_iso(),
        "direction": "archive-indexer-to-logseq",
        "read_only_source": True,
        "sources": sources,
        "items": items,
        "bucket_definitions": bucket_definitions,
        "bucket_stats": bucket_stats,
        "embedding_stats": embedding_stats,
    }


def write_logseq_snapshot(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = build_logseq_snapshot()
    output_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
