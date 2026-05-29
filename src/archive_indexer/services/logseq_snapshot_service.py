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
        sources = _rows_to_dicts(
            db.conn.execute("SELECT * FROM sources ORDER BY label, id").fetchall()
        )
        items = _rows_to_dicts(
            db.conn.execute(
                "SELECT * FROM items ORDER BY indexed_at DESC, path_or_url"
            ).fetchall()
        )
        chunks = _rows_to_dicts(db.conn.execute("""
                SELECT id, item_id, chunk_type, text, timestamp_start, timestamp_end, metadata_json, created_at
                FROM chunks
                ORDER BY created_at, id
                """).fetchall())
        item_buckets = _rows_to_dicts(db.conn.execute("""
                SELECT item_id, bucket_name, confidence, evidence_json, assigned_by, assigned_at
                FROM item_buckets
                ORDER BY bucket_name, item_id
                """).fetchall())
        bucket_definitions = _rows_to_dicts(
            db.conn.execute("SELECT * FROM bucket_definitions ORDER BY name").fetchall()
        )
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
    output_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8"
    )
    return output_path


def _logseq_property_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value).replace("\n", " ").strip()


def _logseq_filename(title: str) -> str:
    safe = "".join(
        char if char.isalnum() or char in {" ", "-", "_"} else "-" for char in title
    )
    safe = " ".join(safe.split()).strip()
    return f"{safe[:120] or 'Archive Indexer Page'}.md"


def _logseq_page_ref(title: str) -> str:
    return f"[[{title}]]"


def _write_logseq_page(pages_dir: Path, title: str, lines: list[str]) -> Path:
    page_path = pages_dir / _logseq_filename(title)
    page_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return page_path


def _item_page_title(item: dict[str, Any]) -> str:
    label = item.get("filename") or item.get("path_or_url") or item.get("id")
    label = Path(str(label)).name if str(label) else str(item.get("id"))
    return f"Archive Indexer Item - {label} - {str(item.get('id', ''))[:8]}"


def write_logseq_graph(output_dir: Path) -> Path:
    """Export the Archive Indexer database as plain Logseq Markdown pages.

    This is a Python-only, one-way export path. It writes Logseq-readable Markdown
    files under ``output_dir/pages`` and never requires a JavaScript plugin or a
    Logseq runtime connection back into the Archive Indexer database.
    """
    snapshot = build_logseq_snapshot()
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    item_titles = {item["id"]: _item_page_title(item) for item in snapshot["items"]}

    index_lines = [
        "archive-indexer:: true",
        "archive-indexer-direction:: archive-indexer-to-logseq",
        "archive-indexer-exporter:: python-logseq-graph",
        f"archive-indexer-generated-at:: {snapshot['generated_at']}",
        "",
        f"- Exported {len(snapshot['items'])} items from Archive Indexer.",
        "- This graph is read-only from Archive Indexer into Logseq; edit Archive Indexer data in SQLite/config and re-export.",
        "- Buckets",
    ]
    for stat in snapshot["bucket_stats"]:
        bucket_title = f"Archive Indexer Bucket - {stat['bucket_name']}"
        index_lines.append(f"  - {_logseq_page_ref(bucket_title)} ({stat['c']} items)")
    index_lines.append("- Sources")
    for source in snapshot["sources"]:
        source_title = f"Archive Indexer Source - {source.get('label') or source['id']}"
        index_lines.append(f"  - {_logseq_page_ref(source_title)}")
    index_lines.append("- Items")
    for item in snapshot["items"]:
        index_lines.append(f"  - {_logseq_page_ref(item_titles[item['id']])}")
    _write_logseq_page(pages_dir, "Archive Indexer", index_lines)

    for source in snapshot["sources"]:
        source_title = f"Archive Indexer Source - {source.get('label') or source['id']}"
        source_items = [
            item for item in snapshot["items"] if item.get("source_id") == source["id"]
        ]
        lines = [
            "archive-indexer:: true",
            "archive-indexer-page-type:: source",
            "archive-indexer-direction:: archive-indexer-to-logseq",
            f"archive-indexer-source-id:: {_logseq_property_value(source['id'])}",
            f"archive-indexer-source-type:: {_logseq_property_value(source.get('source_type'))}",
            f"archive-indexer-root:: {_logseq_property_value(source.get('root_path_or_file'))}",
            "",
            f"- Source label: {_logseq_property_value(source.get('label'))}",
            f"- Item count: {len(source_items)}",
            "- Items",
        ]
        for item in source_items:
            lines.append(f"  - {_logseq_page_ref(item_titles[item['id']])}")
        _write_logseq_page(pages_dir, source_title, lines)

    bucket_names = {
        bucket["bucket_name"]
        for item in snapshot["items"]
        for bucket in item.get("buckets", [])
    }
    for bucket_name in sorted(bucket_names):
        bucket_items = [
            item
            for item in snapshot["items"]
            if any(
                bucket["bucket_name"] == bucket_name
                for bucket in item.get("buckets", [])
            )
        ]
        bucket_title = f"Archive Indexer Bucket - {bucket_name}"
        definition = next(
            (
                row
                for row in snapshot["bucket_definitions"]
                if row.get("name") == bucket_name
            ),
            {},
        )
        lines = [
            "archive-indexer:: true",
            "archive-indexer-page-type:: bucket",
            "archive-indexer-direction:: archive-indexer-to-logseq",
            f"archive-indexer-bucket:: {_logseq_property_value(bucket_name)}",
            "",
            f"- Description: {_logseq_property_value(definition.get('description'))}",
            f"- Item count: {len(bucket_items)}",
            "- Items",
        ]
        for item in bucket_items:
            confidence = next(
                (
                    bucket.get("confidence")
                    for bucket in item.get("buckets", [])
                    if bucket.get("bucket_name") == bucket_name
                ),
                None,
            )
            lines.append(
                f"  - {_logseq_page_ref(item_titles[item['id']])} confidence={_logseq_property_value(confidence)}"
            )
        _write_logseq_page(pages_dir, bucket_title, lines)

    for item in snapshot["items"]:
        title = item_titles[item["id"]]
        source = next(
            (row for row in snapshot["sources"] if row["id"] == item.get("source_id")),
            None,
        )
        source_title = (
            f"Archive Indexer Source - {source.get('label') or source['id']}"
            if source
            else None
        )
        lines = [
            "archive-indexer:: true",
            "archive-indexer-page-type:: item",
            "archive-indexer-direction:: archive-indexer-to-logseq",
            f"archive-indexer-item-id:: {_logseq_property_value(item.get('id'))}",
            f"archive-indexer-item-type:: {_logseq_property_value(item.get('item_type'))}",
            f"archive-indexer-path-or-url:: {_logseq_property_value(item.get('path_or_url'))}",
            "",
            f"- Path or URL: `{_logseq_property_value(item.get('path_or_url'))}`",
            f"- Filename: {_logseq_property_value(item.get('filename'))}",
            f"- MIME type: {_logseq_property_value(item.get('mime_type'))}",
            f"- Size bytes: {_logseq_property_value(item.get('size_bytes'))}",
            f"- Modified time: {_logseq_property_value(item.get('modified_time'))}",
        ]
        if source_title:
            lines.append(f"- Source: {_logseq_page_ref(source_title)}")
        lines.append("- Buckets")
        for bucket in item.get("buckets", []):
            bucket_title = f"Archive Indexer Bucket - {bucket['bucket_name']}"
            lines.append(
                f"  - {_logseq_page_ref(bucket_title)} confidence={_logseq_property_value(bucket.get('confidence'))}"
            )
            if bucket.get("evidence"):
                lines.append(
                    f"    - Evidence: `{_logseq_property_value(bucket.get('evidence'))}`"
                )
        lines.append("- Chunks")
        for chunk in item.get("chunks", []):
            text = _logseq_property_value(chunk.get("text"))
            lines.append(f"  - {chunk.get('chunk_type')} `{text[:500]}`")
            if chunk.get("timestamp_start") is not None:
                lines.append(
                    f"    - Timestamp: {chunk.get('timestamp_start')}–{chunk.get('timestamp_end')}"
                )
        _write_logseq_page(pages_dir, title, lines)

    return output_dir
