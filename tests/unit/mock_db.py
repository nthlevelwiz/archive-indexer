from __future__ import annotations

from copy import deepcopy
from typing import Any

from archive_indexer.adapters.db import Row


class ResultSet:
    def __init__(self, rows):
        self._rows = list(rows)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class MockGraphAdapter:
    def __init__(self):
        self.sources: dict[str, dict[str, Any]] = {}
        self.items: dict[str, dict[str, Any]] = {}
        self.chunks: dict[str, dict[str, Any]] = {}
        self.bucket_definitions: dict[str, dict[str, Any]] = {}
        self.bucket_rules: dict[str, dict[str, Any]] = {}
        self.item_buckets: dict[tuple[str, str], dict[str, Any]] = {}
        self.embeddings: dict[str, dict[str, Any]] = {}
        self.closed = False

    def init_schema(self):
        return None

    def close(self):
        self.closed = True

    def commit(self):
        return None

    def execute(self, sql: str, params: tuple = ()):  # test compatibility only
        normalized = " ".join(sql.strip().lower().split())
        if normalized.startswith("insert into items"):
            if params:
                values = params
            else:
                raw_values = sql.split("VALUES", 1)[1].strip().strip("()")
                values = tuple(part.strip().strip("'\"") for part in raw_values.split(","))
            item_id, source_id, item_type, path_or_url, filename, extension, *rest = values
            self.upsert_item((item_id, source_id, item_type, path_or_url, filename, extension, "", 0, "", "", "{}", rest[-1] if rest else "now"))
            return ResultSet([])
        if normalized.startswith("select path_or_url, item_type from items"):
            return ResultSet(Row({"path_or_url": i.get("path_or_url"), "item_type": i.get("item_type")}) for i in sorted(self.items.values(), key=lambda r: r.get("path_or_url") or ""))
        if normalized.startswith("select chunk_type from chunks"):
            return ResultSet(Row({"chunk_type": c.get("chunk_type")}) for c in self.chunks.values())
        if normalized.startswith("select bucket_name, count(*) from item_buckets"):
            return ResultSet(self.fetch_bucket_stats())
        if normalized.startswith("select item_id,bucket_name from item_buckets"):
            rows = [Row({"item_id": v["item_id"], "bucket_name": v["bucket_name"]}) for v in self.item_buckets.values()]
            rows.sort(key=lambda r: r["item_id"])
            return ResultSet(rows)
        if normalized.startswith("select path_or_url from items limit 1"):
            rows = [Row({"path_or_url": i.get("path_or_url")}) for i in self.items.values()]
            return ResultSet(rows[:1])
        if normalized.startswith("select count(*) from items"):
            return ResultSet([Row({"count": len(self.items)})])
        if normalized.startswith("select count(*) from chunks where chunk_type='frame_ocr'"):
            return ResultSet([Row({"count": sum(1 for c in self.chunks.values() if c.get("chunk_type") == "frame_ocr")})])
        if normalized.startswith("select count(*) from chunks"):
            return ResultSet([Row({"count": len(self.chunks)})])
        if normalized.startswith("select count(*) from item_buckets"):
            return ResultSet([Row({"count": len(self.item_buckets)})])
        if normalized.startswith("select count(*) from embeddings"):
            return ResultSet([Row({"count": len(self.embeddings)})])
        raise NotImplementedError(sql)

    def upsert_source(self, source_id, root_path, label, config_json):
        self.sources[source_id] = {"id": source_id, "source_type": "folder", "root_path_or_file": root_path, "label": label, "config_json": config_json}

    def upsert_bookmark_source(self, source_id: str, bookmark_path: str, label: str, config_json: str):
        self.sources[source_id] = {"id": source_id, "source_type": "bookmark_html", "root_path_or_file": bookmark_path, "label": label, "config_json": config_json}

    def upsert_item(self, values: tuple):
        keys = ["id", "source_id", "item_type", "path_or_url", "filename", "extension", "mime_type", "size_bytes", "modified_time", "content_hash", "metadata_json", "indexed_at"]
        self.items[values[0]] = dict(zip(keys, values, strict=True))

    def upsert_chunk(self, values: tuple):
        keys = ["id", "item_id", "chunk_type", "text", "metadata_json", "created_at"]
        self.chunks[values[0]] = dict(zip(keys, values, strict=True))

    def insert_fts(self, chunk_id: str, text: str):
        if chunk_id in self.chunks:
            self.chunks[chunk_id]["text"] = text

    def upsert_bucket_definition(self, name: str, description: str, bucket_type: str):
        self.bucket_definitions[name] = {"id": name, "name": name, "description": description, "bucket_type": bucket_type}

    def insert_bucket_rule(self, rule_id: str, bucket_name: str, rule_type: str, pattern: str, weight: float, applies_to: str):
        self.bucket_rules[rule_id] = {"id": rule_id, "bucket_name": bucket_name, "rule_type": rule_type, "pattern": pattern, "weight": weight, "applies_to": applies_to}

    def upsert_item_bucket(self, item_id: str, bucket_name: str, confidence: float, evidence_json: str, assigned_by: str, assigned_at: str):
        self.item_buckets[(item_id, bucket_name)] = {"item_id": item_id, "bucket_name": bucket_name, "confidence": confidence, "evidence_json": evidence_json, "assigned_by": assigned_by, "assigned_at": assigned_at}

    def get_item_row_by_path(self, path_or_url: str):
        for item in self.items.values():
            if item.get("path_or_url") == path_or_url:
                return Row({"id": item["id"], "modified_time": item.get("modified_time"), "size_bytes": item.get("size_bytes")})
        return None

    def get_chunk_by_item_and_type(self, item_id: str, chunk_type: str):
        for chunk in self.chunks.values():
            if chunk.get("item_id") == item_id and chunk.get("chunk_type") == chunk_type:
                return Row({"id": chunk["id"]})
        return None

    def fetch_items_for_bucket_assignment(self):
        return [Row({k: item.get(k) for k in ["id", "path_or_url", "filename", "extension", "metadata_json"]}) for item in self.items.values()]

    def search_chunks(self, query: str, bucket: str | None = None):
        rows = []
        query_l = query.lower()
        for chunk in self.chunks.values():
            if query_l not in str(chunk.get("text", "")).lower():
                continue
            item = self.items.get(chunk.get("item_id"))
            if not item:
                continue
            if bucket and (item["id"], bucket) not in self.item_buckets:
                continue
            rows.append(Row({"path_or_url": item.get("path_or_url"), "text": chunk.get("text")}))
        return rows

    def fetch_chunks_for_embedding(self):
        return [Row({"id": c["id"], "text": c.get("text", "")}) for c in self.chunks.values()]

    def fetch_semantic_search_rows(self, model: str):
        rows = []
        for emb in self.embeddings.values():
            if emb.get("model") != model:
                continue
            chunk = self.chunks.get(emb.get("chunk_id"))
            item = self.items.get(chunk.get("item_id")) if chunk else None
            if chunk and item:
                rows.append(Row({"path_or_url": item.get("path_or_url"), "text": chunk.get("text"), "embedding_json": emb.get("embedding_json")}))
        return rows

    def embedding_exists(self, chunk_id: str, model: str):
        return any(e.get("chunk_id") == chunk_id and e.get("model") == model for e in self.embeddings.values())

    def insert_embedding(self, embedding_id: str, chunk_id: str, model: str, embedding_json: str, dimensions: int):
        self.embeddings[embedding_id] = {"id": embedding_id, "chunk_id": chunk_id, "model": model, "embedding_json": embedding_json, "dimensions": dimensions}

    def fetch_video_items(self):
        return [Row({"id": i["id"], "path_or_url": i.get("path_or_url")}) for i in self.items.values() if i.get("item_type") == "video"]

    def insert_frame_ocr_chunk(self, chunk_id: str, item_id: str, text: str):
        self.chunks[chunk_id] = {"id": chunk_id, "item_id": item_id, "chunk_type": "frame_ocr", "text": text, "metadata_json": "{}", "created_at": "now"}

    def fetch_item_by_path_or_url(self, path_or_url: str):
        for item in self.items.values():
            if item.get("path_or_url") == path_or_url:
                return Row(deepcopy(item))
        return None

    def fetch_item_bucket_explanations(self, path_or_url: str):
        item = self.fetch_item_by_path_or_url(path_or_url)
        if not item:
            return []
        return [Row({"bucket_name": b["bucket_name"], "confidence": b["confidence"], "evidence_json": b["evidence_json"]}) for (item_id, _), b in self.item_buckets.items() if item_id == item["id"]]

    def fetch_bucket_contents(self, bucket_name: str):
        return [Row({"path_or_url": self.items[item_id].get("path_or_url")}) for (item_id, bname), _ in self.item_buckets.items() if bname == bucket_name and item_id in self.items]

    def fetch_bucket_stats(self):
        counts: dict[str, int] = {}
        for _, bucket_name in self.item_buckets:
            counts[bucket_name] = counts.get(bucket_name, 0) + 1
        return [Row({"bucket_name": k, "c": v}) for k, v in sorted(counts.items(), key=lambda item: item[1], reverse=True)]
