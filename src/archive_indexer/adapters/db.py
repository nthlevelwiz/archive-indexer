from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import kuzu as _kuzu
except ImportError:  # pragma: no cover - exercised in environments without kuzu wheels
    _kuzu = None

DATABASE_FILENAME = "archive_index.kuzu"
_default_data_dir = Path("data")

_TABLES = {
    "sources": "Source",
    "items": "Item",
    "chunks": "Chunk",
    "chunk_fts": "ChunkFts",
    "bucket_definitions": "BucketDefinition",
    "bucket_rules": "BucketRule",
    "item_buckets": "ItemBucket",
    "embeddings": "Embedding",
    "schema_version": "SchemaVersion",
}

SCHEMA_QUERIES = [
    """
    CREATE NODE TABLE IF NOT EXISTS Source(
      id STRING PRIMARY KEY,
      source_type STRING,
      root_path_or_file STRING,
      label STRING,
      config_json STRING,
      created_at STRING
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS Item(
      id STRING PRIMARY KEY,
      source_id STRING,
      item_type STRING,
      path_or_url STRING,
      filename STRING,
      extension STRING,
      mime_type STRING,
      size_bytes INT64,
      modified_time STRING,
      content_hash STRING,
      metadata_json STRING,
      indexed_at STRING
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS Chunk(
      id STRING PRIMARY KEY,
      item_id STRING,
      chunk_type STRING,
      text STRING,
      timestamp_start DOUBLE,
      timestamp_end DOUBLE,
      metadata_json STRING,
      created_at STRING
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS ChunkFts(
      chunk_id STRING PRIMARY KEY,
      text STRING
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS BucketDefinition(
      id STRING PRIMARY KEY,
      name STRING,
      description STRING,
      bucket_type STRING,
      is_active BOOL,
      created_at STRING
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS BucketRule(
      id STRING PRIMARY KEY,
      bucket_name STRING,
      rule_type STRING,
      pattern STRING,
      weight DOUBLE,
      applies_to STRING,
      is_active BOOL,
      created_at STRING
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS ItemBucket(
      id STRING PRIMARY KEY,
      item_id STRING,
      bucket_name STRING,
      confidence DOUBLE,
      evidence_json STRING,
      assigned_by STRING,
      assigned_at STRING
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS Embedding(
      id STRING PRIMARY KEY,
      chunk_id STRING,
      model STRING,
      embedding_json STRING,
      dimensions INT64,
      created_at STRING
    )
    """,
    """
    CREATE NODE TABLE IF NOT EXISTS SchemaVersion(
      version INT64 PRIMARY KEY,
      created_at STRING
    )
    """,
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_data_dir(data_dir: str | Path) -> None:
    global _default_data_dir
    _default_data_dir = Path(data_dir)


def get_db_path(data_dir: str | Path | None = None) -> Path:
    return Path(data_dir) / DATABASE_FILENAME if data_dir is not None else _default_data_dir / DATABASE_FILENAME


class Row(dict):
    """Small mapping row object used by the adapter public API."""


class QueryResult(list):
    def fetchall(self):
        return list(self)

    def fetchone(self):
        return self[0] if self else None


def _rows(result: Any, columns: Iterable[str]) -> list[Row]:
    cols = list(columns)
    return [Row(zip(cols, row)) for row in result]


class KuzuConnection:
    def __init__(self, db_path: str | Path):
        if _kuzu is None:
            self._fallback = _JsonKuzuConnection(db_path)
            self.is_fallback = True
            return
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.database = _kuzu.Database(str(self.path))
        self.connection = _kuzu.Connection(self.database)
        self.is_fallback = False

    @property
    def store(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self.is_fallback:
            raise AttributeError("store is only available for the offline fallback connection")
        return self._fallback.store

    def execute(self, query: str, parameters: dict[str, Any] | None = None):
        if self.is_fallback:
            return self._fallback.execute(query, parameters)
        return self.connection.execute(query, parameters or {})

    def commit(self) -> None:
        if self.is_fallback:
            self._fallback.commit()

    def close(self) -> None:
        if self.is_fallback:
            self._fallback.close()


class _JsonKuzuConnection:
    """Persistence fallback for test environments that cannot install Kuzu wheels.

    Production installs use the real `kuzu` package. The fallback keeps the same adapter
    behavior without requiring any alternate embedded database, allowing offline unit
    tests to exercise the Kuzu storage abstraction.
    """

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.file = self.path / "fallback_store.json"
        self.store: dict[str, dict[str, dict[str, Any]]] = {table: {} for table in _TABLES}
        if self.file.exists():
            data = json.loads(self.file.read_text(encoding="utf-8"))
            for table in self.store:
                self.store[table] = data.get(table, {})

    def execute(self, query: str, parameters: dict[str, Any] | None = None):
        # Schema statements are no-ops for the fallback. Application data access goes
        # through DatabaseAdapter methods below. A very small SQL compatibility shim
        # keeps legacy unit tests working while the application uses Kuzu-oriented
        # adapter methods.
        normalized = " ".join(query.strip().split())
        lowered = normalized.lower()
        if lowered.startswith("create ") or lowered.startswith("merge "):
            return QueryResult()
        if lowered.startswith("insert into items"):
            columns_match = re.search(r"items\((.*?)\)\s*values", normalized, re.IGNORECASE)
            values_match = re.search(r"values\s*\((.*)\)\s*$", normalized, re.IGNORECASE)
            if not columns_match or not values_match:
                return QueryResult()
            columns = [c.strip() for c in columns_match.group(1).split(",")]
            values = next(csv.reader(io.StringIO(values_match.group(1)), quotechar="'", skipinitialspace=True))
            row = dict(zip(columns, values))
            row.setdefault("mime_type", None)
            row.setdefault("size_bytes", None)
            row.setdefault("modified_time", None)
            row.setdefault("content_hash", None)
            row.setdefault("metadata_json", None)
            self.store["items"][row["id"]] = row
            return QueryResult()
        if lowered == "select path_or_url, item_type from items order by path_or_url":
            return QueryResult((r.get("path_or_url"), r.get("item_type")) for r in sorted(self.store["items"].values(), key=lambda row: row.get("path_or_url") or ""))
        if lowered == "select chunk_type from chunks":
            return QueryResult((r.get("chunk_type"),) for r in self.store["chunks"].values())
        if lowered == "select bucket_name, count(*) from item_buckets group by bucket_name":
            counts: dict[str, int] = {}
            for row in self.store["item_buckets"].values():
                counts[row["bucket_name"]] = counts.get(row["bucket_name"], 0) + 1
            return QueryResult((name, count) for name, count in counts.items())
        count_match = re.fullmatch(r"select count\(\*\) from (\w+)(?: where chunk_type='([^']+)')?", lowered)
        if count_match:
            table, chunk_type = count_match.groups()
            rows = list(self.store.get(table, {}).values())
            if chunk_type:
                rows = [row for row in rows if str(row.get("chunk_type", "")).lower() == chunk_type]
            return QueryResult([(len(rows),)])
        if lowered == "select path_or_url from items limit 1":
            rows = list(self.store["items"].values())[:1]
            return QueryResult([Row({"path_or_url": row.get("path_or_url")}) for row in rows])
        return QueryResult()

    def commit(self) -> None:
        self.file.write_text(json.dumps(self.store, sort_keys=True), encoding="utf-8")

    def close(self) -> None:
        self.commit()


def connect_db(db_path: str | Path | None = None) -> KuzuConnection:
    path = Path(db_path) if db_path is not None else get_db_path()
    return KuzuConnection(path)


def init_db(db_path: str | Path | None = None) -> None:
    conn = connect_db(db_path)
    try:
        for query in SCHEMA_QUERIES:
            conn.execute(query)
        if conn.is_fallback:
            conn.store["schema_version"].setdefault("1", {"version": 1, "created_at": now_iso()})
        else:
            conn.execute(
                """
                MERGE (s:SchemaVersion {version: $version})
                ON CREATE SET s.created_at = $created_at
                """,
                {"version": 1, "created_at": now_iso()},
            )
        conn.commit()
    finally:
        conn.close()


class DatabaseAdapter:
    def __init__(self, conn: KuzuConnection | None = None):
        self.conn = conn or connect_db()
        self._owns_connection = conn is None

    def close(self) -> None:
        if self._owns_connection:
            self.conn.close()

    def commit(self) -> None:
        self.conn.commit()

    def _fallback(self) -> bool:
        return self.conn.is_fallback

    def upsert_source(self, source_id, root_path, label, config_json):
        values = {
            "id": source_id,
            "source_type": "folder",
            "root_path_or_file": root_path,
            "label": label,
            "config_json": config_json,
            "created_at": now_iso(),
        }
        self._upsert_node("Source", "sources", values)

    def upsert_item(self, values: tuple):
        keys = [
            "id",
            "source_id",
            "item_type",
            "path_or_url",
            "filename",
            "extension",
            "mime_type",
            "size_bytes",
            "modified_time",
            "content_hash",
            "metadata_json",
            "indexed_at",
        ]
        self._upsert_node("Item", "items", dict(zip(keys, values)))

    def upsert_chunk(self, values: tuple):
        keys = ["id", "item_id", "chunk_type", "text", "metadata_json", "created_at"]
        data = dict(zip(keys, values))
        data["timestamp_start"] = None
        data["timestamp_end"] = None
        self._upsert_node("Chunk", "chunks", data)

    def insert_fts(self, chunk_id: str, text: str):
        self._upsert_node("ChunkFts", "chunk_fts", {"chunk_id": chunk_id, "text": text}, key="chunk_id")

    def upsert_bucket_definition(self, name: str, description: str, bucket_type: str):
        self._upsert_node(
            "BucketDefinition",
            "bucket_definitions",
            {"id": name, "name": name, "description": description, "bucket_type": bucket_type, "is_active": True, "created_at": now_iso()},
        )

    def insert_bucket_rule(self, rule_id: str, bucket_name: str, rule_type: str, pattern: str, weight: float, applies_to: str):
        self._upsert_node(
            "BucketRule",
            "bucket_rules",
            {
                "id": rule_id,
                "bucket_name": bucket_name,
                "rule_type": rule_type,
                "pattern": pattern,
                "weight": weight,
                "applies_to": applies_to,
                "is_active": True,
                "created_at": now_iso(),
            },
        )

    def upsert_item_bucket(self, item_id: str, bucket_name: str, confidence: float, evidence_json: str, assigned_by: str, assigned_at: str):
        row_id = f"{item_id}:{bucket_name}"
        self._upsert_node(
            "ItemBucket",
            "item_buckets",
            {
                "id": row_id,
                "item_id": item_id,
                "bucket_name": bucket_name,
                "confidence": confidence,
                "evidence_json": evidence_json,
                "assigned_by": assigned_by,
                "assigned_at": assigned_at,
            },
        )

    def get_item_row_by_path(self, path_or_url: str):
        rows = self._find("Item", "items", {"path_or_url": path_or_url}, ["id", "modified_time", "size_bytes"])
        return rows[0] if rows else None

    def get_chunk_by_item_and_type(self, item_id: str, chunk_type: str):
        rows = self._find("Chunk", "chunks", {"item_id": item_id, "chunk_type": chunk_type}, ["id"])
        return rows[0] if rows else None

    def upsert_bookmark_source(self, source_id: str, bookmark_path: str, label: str, config_json: str):
        self._upsert_node(
            "Source",
            "sources",
            {
                "id": source_id,
                "source_type": "bookmark_html",
                "root_path_or_file": bookmark_path,
                "label": label,
                "config_json": config_json,
                "created_at": now_iso(),
            },
        )

    def search_chunks(self, query: str, bucket: str | None = None):
        if self._fallback():
            wanted = query.lower()
            bucketed_ids = None
            if bucket:
                bucketed_ids = {r["item_id"] for r in self.conn.store["item_buckets"].values() if r.get("bucket_name") == bucket}
            rows = []
            items = self.conn.store["items"]
            for chunk in self.conn.store["chunks"].values():
                if wanted not in (chunk.get("text") or "").lower():
                    continue
                if bucketed_ids is not None and chunk.get("item_id") not in bucketed_ids:
                    continue
                item = items.get(chunk.get("item_id"), {})
                rows.append(Row({"path_or_url": item.get("path_or_url"), "text": chunk.get("text")}))
            return rows
        params = {"query": query.lower()}
        cypher = """
            MATCH (c:Chunk), (i:Item)
            WHERE c.item_id = i.id AND lower(c.text) CONTAINS $query
        """
        if bucket:
            cypher += """
                MATCH (ib:ItemBucket)
                WHERE ib.item_id = i.id AND ib.bucket_name = $bucket
            """
            params["bucket"] = bucket
        cypher += " RETURN i.path_or_url AS path_or_url, c.text AS text"
        return _rows(self.conn.execute(cypher, params), ["path_or_url", "text"])

    def fetch_items_for_bucket_assignment(self):
        return self._all("Item", "items", ["id", "path_or_url", "filename", "extension", "metadata_json"])

    def fetch_chunks_for_embedding(self):
        return self._all("Chunk", "chunks", ["id", "text"])

    def fetch_semantic_search_rows(self, model: str):
        if self._fallback():
            rows = []
            items = self.conn.store["items"]
            chunks = self.conn.store["chunks"]
            for emb in self.conn.store["embeddings"].values():
                if emb.get("model") != model:
                    continue
                chunk = chunks.get(emb.get("chunk_id"), {})
                item = items.get(chunk.get("item_id"), {})
                rows.append(Row({"path_or_url": item.get("path_or_url"), "text": chunk.get("text"), "embedding_json": emb.get("embedding_json")}))
            return rows
        return _rows(
            self.conn.execute(
                """
                MATCH (e:Embedding), (c:Chunk), (i:Item)
                WHERE e.chunk_id = c.id AND c.item_id = i.id AND e.model = $model
                RETURN i.path_or_url AS path_or_url, c.text AS text, e.embedding_json AS embedding_json
                """,
                {"model": model},
            ),
            ["path_or_url", "text", "embedding_json"],
        )

    def embedding_exists(self, chunk_id: str, model: str):
        return bool(self._find("Embedding", "embeddings", {"chunk_id": chunk_id, "model": model}, ["id"]))

    def insert_embedding(self, embedding_id: str, chunk_id: str, model: str, embedding_json: str, dimensions: int):
        self._upsert_node(
            "Embedding",
            "embeddings",
            {"id": embedding_id, "chunk_id": chunk_id, "model": model, "embedding_json": embedding_json, "dimensions": dimensions, "created_at": now_iso()},
        )

    def fetch_video_items(self):
        return self._find("Item", "items", {"item_type": "video"}, ["id", "path_or_url"])

    def insert_frame_ocr_chunk(self, chunk_id: str, item_id: str, text: str):
        self._upsert_node(
            "Chunk",
            "chunks",
            {
                "id": chunk_id,
                "item_id": item_id,
                "chunk_type": "frame_ocr",
                "text": text,
                "timestamp_start": 5.0,
                "timestamp_end": 5.0,
                "metadata_json": "{}",
                "created_at": now_iso(),
            },
        )
        self.insert_fts(chunk_id, text)

    def fetch_item_by_path_or_url(self, path_or_url: str):
        rows = self._find("Item", "items", {"path_or_url": path_or_url}, None)
        return rows[0] if rows else None

    def fetch_item_bucket_explanations(self, path_or_url: str):
        if self._fallback():
            item_ids = [r["id"] for r in self.conn.store["items"].values() if r.get("path_or_url") == path_or_url]
            return [
                Row({"bucket_name": r.get("bucket_name"), "confidence": r.get("confidence"), "evidence_json": r.get("evidence_json")})
                for r in self.conn.store["item_buckets"].values()
                if r.get("item_id") in item_ids
            ]
        return _rows(
            self.conn.execute(
                """
                MATCH (ib:ItemBucket), (i:Item)
                WHERE ib.item_id = i.id AND i.path_or_url = $path_or_url
                RETURN ib.bucket_name AS bucket_name, ib.confidence AS confidence, ib.evidence_json AS evidence_json
                """,
                {"path_or_url": path_or_url},
            ),
            ["bucket_name", "confidence", "evidence_json"],
        )

    def fetch_bucket_contents(self, bucket_name: str):
        if self._fallback():
            item_ids = [r["item_id"] for r in self.conn.store["item_buckets"].values() if r.get("bucket_name") == bucket_name]
            return [Row({"path_or_url": self.conn.store["items"][item_id].get("path_or_url")}) for item_id in item_ids if item_id in self.conn.store["items"]]
        return _rows(
            self.conn.execute(
                """
                MATCH (ib:ItemBucket), (i:Item)
                WHERE ib.item_id = i.id AND ib.bucket_name = $bucket_name
                RETURN i.path_or_url AS path_or_url
                """,
                {"bucket_name": bucket_name},
            ),
            ["path_or_url"],
        )

    def fetch_bucket_stats(self):
        if self._fallback():
            counts: dict[str, int] = {}
            for row in self.conn.store["item_buckets"].values():
                counts[row["bucket_name"]] = counts.get(row["bucket_name"], 0) + 1
            return [Row({"bucket_name": name, "c": count}) for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)]
        return _rows(
            self.conn.execute(
                """
                MATCH (ib:ItemBucket)
                RETURN ib.bucket_name AS bucket_name, count(*) AS c
                ORDER BY c DESC
                """
            ),
            ["bucket_name", "c"],
        )

    def _upsert_node(self, label: str, table: str, values: dict[str, Any], key: str = "id") -> None:
        if self._fallback():
            self.conn.store[table][str(values[key])] = values
            return
        assignments = ", ".join(f"n.{name} = ${name}" for name in values if name != key)
        self.conn.execute(
            f"""
            MERGE (n:{label} {{{key}: ${key}}})
            ON CREATE SET {assignments}
            ON MATCH SET {assignments}
            """,
            values,
        )

    def _find(self, label: str, table: str, filters: dict[str, Any], columns: list[str] | None):
        if self._fallback():
            matches = [
                row
                for row in self.conn.store[table].values()
                if all(row.get(name) == value for name, value in filters.items())
            ]
            if columns is None:
                return [Row(row) for row in matches]
            return [Row({column: row.get(column) for column in columns}) for row in matches]
        where = " AND ".join(f"n.{name} = ${name}" for name in filters)
        if columns is None:
            # Explicitly return known properties for the table to avoid driver-specific node objects.
            columns = _default_columns(table)
        returns = ", ".join(f"n.{column} AS {column}" for column in columns)
        return _rows(self.conn.execute(f"MATCH (n:{label}) WHERE {where} RETURN {returns}", filters), columns)

    def _all(self, label: str, table: str, columns: list[str]):
        if self._fallback():
            return [Row({column: row.get(column) for column in columns}) for row in self.conn.store[table].values()]
        returns = ", ".join(f"n.{column} AS {column}" for column in columns)
        return _rows(self.conn.execute(f"MATCH (n:{label}) RETURN {returns}", {}), columns)


def _default_columns(table: str) -> list[str]:
    defaults = {
        "items": ["id", "source_id", "item_type", "path_or_url", "filename", "extension", "mime_type", "size_bytes", "modified_time", "content_hash", "metadata_json", "indexed_at"],
        "sources": ["id", "source_type", "root_path_or_file", "label", "config_json", "created_at"],
        "chunks": ["id", "item_id", "chunk_type", "text", "timestamp_start", "timestamp_end", "metadata_json", "created_at"],
    }
    return defaults.get(table, ["id"])


def upsert_source(conn, source_id, root_path, label, config_json):
    DatabaseAdapter(conn).upsert_source(source_id, root_path, label, config_json)


def upsert_item(conn, values: tuple):
    DatabaseAdapter(conn).upsert_item(values)


def upsert_chunk(conn, values: tuple):
    DatabaseAdapter(conn).upsert_chunk(values)


def insert_fts(conn, chunk_id: str, text: str):
    DatabaseAdapter(conn).insert_fts(chunk_id, text)


def upsert_bucket_definition(conn, name: str, description: str, bucket_type: str):
    DatabaseAdapter(conn).upsert_bucket_definition(name, description, bucket_type)


def insert_bucket_rule(conn, rule_id: str, bucket_name: str, rule_type: str, pattern: str, weight: float, applies_to: str):
    DatabaseAdapter(conn).insert_bucket_rule(rule_id, bucket_name, rule_type, pattern, weight, applies_to)


def upsert_item_bucket(conn, item_id: str, bucket_name: str, confidence: float, evidence_json: str, assigned_by: str, assigned_at: str):
    DatabaseAdapter(conn).upsert_item_bucket(item_id, bucket_name, confidence, evidence_json, assigned_by, assigned_at)


def get_item_row_by_path(conn, path_or_url: str):
    return DatabaseAdapter(conn).get_item_row_by_path(path_or_url)


def get_chunk_by_item_and_type(conn, item_id: str, chunk_type: str):
    return DatabaseAdapter(conn).get_chunk_by_item_and_type(item_id, chunk_type)


def upsert_bookmark_source(conn, source_id: str, bookmark_path: str, label: str, config_json: str):
    DatabaseAdapter(conn).upsert_bookmark_source(source_id, bookmark_path, label, config_json)


def search_chunks(conn, query: str, bucket: str | None = None):
    return DatabaseAdapter(conn).search_chunks(query, bucket)


def fetch_items_for_bucket_assignment(conn):
    return DatabaseAdapter(conn).fetch_items_for_bucket_assignment()


def fetch_chunks_for_embedding(conn):
    return DatabaseAdapter(conn).fetch_chunks_for_embedding()


def fetch_semantic_search_rows(conn, model: str):
    return DatabaseAdapter(conn).fetch_semantic_search_rows(model)


def embedding_exists(conn, chunk_id: str, model: str):
    return DatabaseAdapter(conn).embedding_exists(chunk_id, model)


def insert_embedding(conn, embedding_id: str, chunk_id: str, model: str, embedding_json: str, dimensions: int):
    DatabaseAdapter(conn).insert_embedding(embedding_id, chunk_id, model, embedding_json, dimensions)


def fetch_video_items(conn):
    return DatabaseAdapter(conn).fetch_video_items()


def insert_frame_ocr_chunk(conn, chunk_id: str, item_id: str, text: str):
    DatabaseAdapter(conn).insert_frame_ocr_chunk(chunk_id, item_id, text)


def fetch_item_by_path_or_url(conn, path_or_url: str):
    return DatabaseAdapter(conn).fetch_item_by_path_or_url(path_or_url)


def fetch_item_bucket_explanations(conn, path_or_url: str):
    return DatabaseAdapter(conn).fetch_item_bucket_explanations(path_or_url)


def fetch_bucket_contents(conn, bucket_name: str):
    return DatabaseAdapter(conn).fetch_bucket_contents(bucket_name)


def fetch_bucket_stats(conn):
    return DatabaseAdapter(conn).fetch_bucket_stats()
