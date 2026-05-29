from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from neo4j import GraphDatabase
except ImportError:  # pragma: no cover - exercised only when optional dependency is absent
    GraphDatabase = None  # type: ignore[assignment]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_NEO4J_URI = "bolt://localhost:7687"
DEFAULT_NEO4J_USER = "neo4j"
DEFAULT_NEO4J_DATABASE = "neo4j"
GRAPH_STORE_FILENAME = "archive_graph.json"
DATABASE_FILENAME = GRAPH_STORE_FILENAME

_default_data_dir = Path("data")
_neo4j_uri = os.getenv("NEO4J_URI")
_neo4j_user = os.getenv("NEO4J_USER", DEFAULT_NEO4J_USER)
_neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
_neo4j_database = os.getenv("NEO4J_DATABASE", DEFAULT_NEO4J_DATABASE)


class Row(dict):
    """Small row helper compatible with dict-style access used by the app."""

    def __getitem__(self, key):  # type: ignore[override]
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class ResultSet:
    def __init__(self, rows: Iterable[Row]):
        self._rows = list(rows)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class GraphStore:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.sources: dict[str, dict[str, Any]] = {}
        self.items: dict[str, dict[str, Any]] = {}
        self.chunks: dict[str, dict[str, Any]] = {}
        self.bucket_definitions: dict[str, dict[str, Any]] = {}
        self.bucket_rules: dict[str, dict[str, Any]] = {}
        self.item_buckets: dict[tuple[str, str], dict[str, Any]] = {}
        self.embeddings: dict[str, dict[str, Any]] = {}
        if path and path.exists():
            self._load(path)

    def _load(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # Ignore legacy SQLite/binary files or partial writes instead of
            # crashing the CLI fallback path. The fallback now writes to
            # archive_graph.json by default, but explicit old paths may still
            # exist in user data directories.
            return
        self.sources = data.get("sources", {})
        self.items = data.get("items", {})
        self.chunks = data.get("chunks", {})
        self.bucket_definitions = data.get("bucket_definitions", {})
        self.bucket_rules = data.get("bucket_rules", {})
        self.item_buckets = {
            tuple(k.split("\u241f", 1)): v for k, v in data.get("item_buckets", {}).items()
        }
        self.embeddings = data.get("embeddings", {})

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "sources": self.sources,
            "items": self.items,
            "chunks": self.chunks,
            "bucket_definitions": self.bucket_definitions,
            "bucket_rules": self.bucket_rules,
            "item_buckets": {"\u241f".join(k): v for k, v in self.item_buckets.items()},
            "embeddings": self.embeddings,
        }
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


_MEMORY_STORES: dict[str, GraphStore] = {}
_PRINTED_FALLBACK_PATHS: set[str] = set()


def set_data_dir(data_dir: str | Path) -> None:
    global _default_data_dir
    _default_data_dir = Path(data_dir)


def set_neo4j_config(
    uri: str | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
) -> None:
    global _neo4j_uri, _neo4j_user, _neo4j_password, _neo4j_database
    if uri is not None:
        _neo4j_uri = uri
    if user is not None:
        _neo4j_user = user
    if password is not None:
        _neo4j_password = password
    if database is not None:
        _neo4j_database = database


def get_db_path(data_dir: str | Path | None = None) -> Path:
    return Path(data_dir) / GRAPH_STORE_FILENAME if data_dir is not None else _default_data_dir / GRAPH_STORE_FILENAME


def _print_fallback_notice(path: Path) -> None:
    resolved = str(path.resolve())
    if resolved in _PRINTED_FALLBACK_PATHS:
        return
    _PRINTED_FALLBACK_PATHS.add(resolved)
    print(
        f"Using fallback file-backed graph database at {resolved}. Set NEO4J_URI to use Neo4j.",
        file=sys.stderr,
    )


def _store_for_path(path: str | Path | None) -> GraphStore:
    store_path = get_db_path() if path is None else Path(path)
    key = str(store_path.resolve())
    store = _MEMORY_STORES.get(key)
    if store is None:
        store = GraphStore(store_path)
        _MEMORY_STORES[key] = store
    return store


def _should_use_neo4j(uri: str | None) -> bool:
    return bool(uri and not uri.startswith(("file://", "memory://")))


def connect_db(db_path: str | Path | None = None):
    if db_path is not None:
        fallback_path = Path(db_path)
        _print_fallback_notice(fallback_path)
        return FileGraphAdapter(_store_for_path(fallback_path))
    uri = _neo4j_uri
    if _should_use_neo4j(uri):
        return Neo4jDatabaseAdapter(uri or DEFAULT_NEO4J_URI, _neo4j_user, _neo4j_password, _neo4j_database)
    fallback_path = get_db_path()
    _print_fallback_notice(fallback_path)
    return FileGraphAdapter(_store_for_path(fallback_path))


def init_db(db_path: str | Path | None = None) -> None:
    adapter = connect_db(db_path)
    try:
        adapter.init_schema()
        adapter.commit()
    finally:
        adapter.close()


class DatabaseAdapter:
    def __new__(cls, conn: Any | None = None):
        if cls is DatabaseAdapter:
            return conn if conn is not None else connect_db()
        return super().__new__(cls)


class BaseGraphAdapter:
    def init_schema(self) -> None:
        return None

    def close(self) -> None:
        return None

    def commit(self) -> None:
        return None


class FileGraphAdapter(BaseGraphAdapter):
    def __init__(self, store: GraphStore | None = None):
        self.store = store or GraphStore()

    def commit(self) -> None:
        self.store.save()

    def execute(self, sql: str, params: tuple = ()):  # compatibility for older tests and scripts
        normalized = " ".join(sql.strip().lower().split())
        if normalized.startswith("insert into items"):
            if params:
                values = params
            else:
                raw_values = sql.split("VALUES", 1)[1].strip().strip("()")
                values = tuple(part.strip().strip("'\"") for part in raw_values.split(","))
            # Older callers may omit nullable columns. Fill them with graph defaults.
            item_id, source_id, item_type, path_or_url, filename, extension, *rest = values
            full = (item_id, source_id, item_type, path_or_url, filename, extension, "", 0, "", "", "{}", rest[-1] if rest else now_iso())
            self.upsert_item(full)
            return ResultSet([])
        if normalized.startswith("select path_or_url, item_type from items"):
            return ResultSet(Row({"path_or_url": i.get("path_or_url"), "item_type": i.get("item_type")}) for i in sorted(self.store.items.values(), key=lambda r: r.get("path_or_url") or ""))
        if normalized.startswith("select chunk_type from chunks"):
            return ResultSet(Row({"chunk_type": c.get("chunk_type")}) for c in self.store.chunks.values())
        if normalized.startswith("select bucket_name, count(*) from item_buckets"):
            return ResultSet(self.fetch_bucket_stats())
        if normalized.startswith("select item_id,bucket_name from item_buckets"):
            rows = [Row({"item_id": v["item_id"], "bucket_name": v["bucket_name"]}) for v in self.store.item_buckets.values()]
            rows.sort(key=lambda r: r["item_id"])
            return ResultSet(rows)
        if normalized.startswith("select path_or_url from items limit 1"):
            rows = [Row({"path_or_url": i.get("path_or_url")}) for i in self.store.items.values()]
            return ResultSet(rows[:1])
        if normalized.startswith("select count(*) from items"):
            return ResultSet([Row({"count": len(self.store.items)})])
        if normalized.startswith("select count(*) from chunks where chunk_type='frame_ocr'"):
            return ResultSet([Row({"count": self.count_chunks_by_type("frame_ocr")})])
        if normalized.startswith("select count(*) from chunks"):
            return ResultSet([Row({"count": len(self.store.chunks)})])
        if normalized.startswith("select count(*) from item_buckets"):
            return ResultSet([Row({"count": len(self.store.item_buckets)})])
        if normalized.startswith("select count(*) from embeddings"):
            return ResultSet([Row({"count": len(self.store.embeddings)})])
        raise NotImplementedError(f"Unsupported compatibility query: {sql}")

    def upsert_source(self, source_id, root_path, label, config_json):
        self.store.sources[source_id] = {
            "id": source_id,
            "source_type": "folder",
            "root_path_or_file": root_path,
            "label": label,
            "config_json": config_json,
            "created_at": now_iso(),
        }

    def upsert_bookmark_source(self, source_id: str, bookmark_path: str, label: str, config_json: str):
        self.store.sources[source_id] = {
            "id": source_id,
            "source_type": "bookmark_html",
            "root_path_or_file": bookmark_path,
            "label": label,
            "config_json": config_json,
            "created_at": now_iso(),
        }

    def upsert_item(self, values: tuple):
        keys = [
            "id", "source_id", "item_type", "path_or_url", "filename", "extension", "mime_type",
            "size_bytes", "modified_time", "content_hash", "metadata_json", "indexed_at",
        ]
        self.store.items[values[0]] = dict(zip(keys, values, strict=True))

    def upsert_chunk(self, values: tuple):
        keys = ["id", "item_id", "chunk_type", "text", "metadata_json", "created_at"]
        row = dict(zip(keys, values, strict=True))
        row.setdefault("timestamp_start", None)
        row.setdefault("timestamp_end", None)
        self.store.chunks[values[0]] = row

    def insert_fts(self, chunk_id: str, text: str):
        if chunk_id in self.store.chunks:
            self.store.chunks[chunk_id]["text"] = text

    def upsert_bucket_definition(self, name: str, description: str, bucket_type: str):
        self.store.bucket_definitions[name] = {
            "id": name,
            "name": name,
            "description": description,
            "bucket_type": bucket_type,
            "is_active": True,
            "created_at": now_iso(),
        }

    def insert_bucket_rule(self, rule_id: str, bucket_name: str, rule_type: str, pattern: str, weight: float, applies_to: str):
        self.store.bucket_rules[rule_id] = {
            "id": rule_id,
            "bucket_name": bucket_name,
            "rule_type": rule_type,
            "pattern": pattern,
            "weight": weight,
            "applies_to": applies_to,
            "is_active": True,
            "created_at": now_iso(),
        }

    def upsert_item_bucket(self, item_id: str, bucket_name: str, confidence: float, evidence_json: str, assigned_by: str, assigned_at: str):
        self.store.item_buckets[(item_id, bucket_name)] = {
            "item_id": item_id,
            "bucket_name": bucket_name,
            "confidence": confidence,
            "evidence_json": evidence_json,
            "assigned_by": assigned_by,
            "assigned_at": assigned_at,
        }

    def get_item_row_by_path(self, path_or_url: str):
        for item in self.store.items.values():
            if item.get("path_or_url") == path_or_url:
                return Row({"id": item["id"], "modified_time": item.get("modified_time"), "size_bytes": item.get("size_bytes")})
        return None

    def get_chunk_by_item_and_type(self, item_id: str, chunk_type: str):
        for chunk in self.store.chunks.values():
            if chunk.get("item_id") == item_id and chunk.get("chunk_type") == chunk_type:
                return Row({"id": chunk["id"]})
        return None

    def fetch_items_for_bucket_assignment(self):
        return [
            Row({k: item.get(k) for k in ["id", "path_or_url", "filename", "extension", "metadata_json"]})
            for item in self.store.items.values()
        ]

    def search_chunks(self, query: str, bucket: str | None = None):
        query_l = query.lower()
        rows = []
        for chunk in self.store.chunks.values():
            if query_l not in str(chunk.get("text", "")).lower():
                continue
            item = self.store.items.get(chunk.get("item_id"))
            if not item:
                continue
            if bucket and (item["id"], bucket) not in self.store.item_buckets:
                continue
            rows.append(Row({"path_or_url": item.get("path_or_url"), "text": chunk.get("text")}))
        return rows

    def fetch_chunks_for_embedding(self):
        return [Row({"id": c["id"], "text": c.get("text", "")}) for c in self.store.chunks.values()]

    def fetch_semantic_search_rows(self, model: str):
        rows = []
        for emb in self.store.embeddings.values():
            if emb.get("model") != model:
                continue
            chunk = self.store.chunks.get(emb.get("chunk_id"))
            item = self.store.items.get(chunk.get("item_id")) if chunk else None
            if chunk and item:
                rows.append(Row({"path_or_url": item.get("path_or_url"), "text": chunk.get("text"), "embedding_json": emb.get("embedding_json")}))
        return rows

    def embedding_exists(self, chunk_id: str, model: str):
        return any(e.get("chunk_id") == chunk_id and e.get("model") == model for e in self.store.embeddings.values())

    def insert_embedding(self, embedding_id: str, chunk_id: str, model: str, embedding_json: str, dimensions: int):
        self.store.embeddings[embedding_id] = {
            "id": embedding_id,
            "chunk_id": chunk_id,
            "model": model,
            "embedding_json": embedding_json,
            "dimensions": dimensions,
            "created_at": now_iso(),
        }

    def fetch_video_items(self):
        return [Row({"id": i["id"], "path_or_url": i.get("path_or_url")}) for i in self.store.items.values() if i.get("item_type") == "video"]

    def insert_frame_ocr_chunk(self, chunk_id: str, item_id: str, text: str):
        self.store.chunks[chunk_id] = {
            "id": chunk_id,
            "item_id": item_id,
            "chunk_type": "frame_ocr",
            "text": text,
            "timestamp_start": 5.0,
            "timestamp_end": 5.0,
            "metadata_json": "{}",
            "created_at": now_iso(),
        }

    def fetch_item_by_path_or_url(self, path_or_url: str):
        for item in self.store.items.values():
            if item.get("path_or_url") == path_or_url:
                return Row(deepcopy(item))
        return None

    def fetch_item_bucket_explanations(self, path_or_url: str):
        item = self.fetch_item_by_path_or_url(path_or_url)
        if not item:
            return []
        return [
            Row({"bucket_name": b["bucket_name"], "confidence": b["confidence"], "evidence_json": b["evidence_json"]})
            for (item_id, _), b in self.store.item_buckets.items()
            if item_id == item["id"]
        ]

    def fetch_bucket_contents(self, bucket_name: str):
        rows = []
        for (item_id, bname), _ in self.store.item_buckets.items():
            if bname == bucket_name and item_id in self.store.items:
                rows.append(Row({"path_or_url": self.store.items[item_id].get("path_or_url")}))
        return rows

    def fetch_bucket_stats(self):
        counts: dict[str, int] = {}
        for _, bucket_name in self.store.item_buckets:
            counts[bucket_name] = counts.get(bucket_name, 0) + 1
        return [Row({"bucket_name": k, "c": v}) for k, v in sorted(counts.items(), key=lambda item: item[1], reverse=True)]

    def count_nodes(self, label: str) -> int:
        return len(getattr(self.store, label))

    def count_chunks_by_type(self, chunk_type: str) -> int:
        return sum(1 for c in self.store.chunks.values() if c.get("chunk_type") == chunk_type)


class Neo4jDatabaseAdapter(BaseGraphAdapter):
    def __init__(self, uri: str, user: str, password: str, database: str = DEFAULT_NEO4J_DATABASE):
        if GraphDatabase is None:
            raise RuntimeError("The neo4j package is required for Neo4j connections")
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.database = database

    def close(self) -> None:
        self.driver.close()

    def commit(self) -> None:
        return None

    @staticmethod
    def _write_tx(tx, cypher: str, params: dict[str, Any]):
        return list(tx.run(cypher, **params))

    @staticmethod
    def _read_tx(tx, cypher: str, params: dict[str, Any]):
        return list(tx.run(cypher, **params))

    def _execute_write(self, cypher: str, **params):
        with self.driver.session(database=self.database) as session:
            return session.execute_write(self._write_tx, cypher, params)

    def _execute_read(self, cypher: str, **params):
        with self.driver.session(database=self.database) as session:
            records = session.execute_read(self._read_tx, cypher, params)
        return [Row(dict(record)) for record in records]

    def init_schema(self) -> None:
        statements = [
            "CREATE CONSTRAINT source_id IF NOT EXISTS FOR (n:Source) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT item_id IF NOT EXISTS FOR (n:Item) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT item_path IF NOT EXISTS FOR (n:Item) REQUIRE n.path_or_url IS UNIQUE",
            "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (n:Chunk) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT bucket_name IF NOT EXISTS FOR (n:BucketDefinition) REQUIRE n.name IS UNIQUE",
            "CREATE CONSTRAINT bucket_rule_id IF NOT EXISTS FOR (n:BucketRule) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT embedding_id IF NOT EXISTS FOR (n:Embedding) REQUIRE n.id IS UNIQUE",
            "CREATE FULLTEXT INDEX chunkText IF NOT EXISTS FOR (n:Chunk) ON EACH [n.text]",
        ]
        for statement in statements:
            self._execute_write(statement)

    def upsert_source(self, source_id, root_path, label, config_json):
        self._upsert_source(source_id, "folder", root_path, label, config_json)

    def upsert_bookmark_source(self, source_id: str, bookmark_path: str, label: str, config_json: str):
        self._upsert_source(source_id, "bookmark_html", bookmark_path, label, config_json)

    def _upsert_source(self, source_id, source_type, root_path, label, config_json):
        self._execute_write(
            """
            MERGE (s:Source {id: $id})
            SET s.source_type=$source_type, s.root_path_or_file=$root_path, s.label=$label,
                s.config_json=$config_json, s.created_at=coalesce(s.created_at, $created_at)
            """,
            id=source_id,
            source_type=source_type,
            root_path=root_path,
            label=label,
            config_json=config_json,
            created_at=now_iso(),
        )

    def upsert_item(self, values: tuple):
        keys = ["id", "source_id", "item_type", "path_or_url", "filename", "extension", "mime_type", "size_bytes", "modified_time", "content_hash", "metadata_json", "indexed_at"]
        params = dict(zip(keys, values, strict=True))
        self._execute_write(
            """
            MERGE (i:Item {id: $id})
            SET i += $props
            WITH i
            MATCH (s:Source {id: $source_id})
            MERGE (s)-[:PRODUCED]->(i)
            """,
            id=params["id"],
            source_id=params["source_id"],
            props=params,
        )

    def upsert_chunk(self, values: tuple):
        keys = ["id", "item_id", "chunk_type", "text", "metadata_json", "created_at"]
        props = dict(zip(keys, values, strict=True))
        self._execute_write(
            """
            MERGE (c:Chunk {id: $id})
            SET c += $props
            WITH c
            MATCH (i:Item {id: $item_id})
            MERGE (i)-[:HAS_CHUNK]->(c)
            """,
            id=props["id"],
            item_id=props["item_id"],
            props=props,
        )

    def insert_fts(self, chunk_id: str, text: str):
        self._execute_write("MATCH (c:Chunk {id: $chunk_id}) SET c.text=$text", chunk_id=chunk_id, text=text)

    def upsert_bucket_definition(self, name: str, description: str, bucket_type: str):
        self._execute_write(
            "MERGE (b:BucketDefinition {name: $name}) SET b.id=$name, b.description=$description, b.bucket_type=$bucket_type, b.is_active=true, b.created_at=coalesce(b.created_at, $created_at)",
            name=name,
            description=description,
            bucket_type=bucket_type,
            created_at=now_iso(),
        )

    def insert_bucket_rule(self, rule_id: str, bucket_name: str, rule_type: str, pattern: str, weight: float, applies_to: str):
        self._execute_write(
            """
            MATCH (b:BucketDefinition {name: $bucket_name})
            MERGE (r:BucketRule {id: $id})
            SET r.bucket_name=$bucket_name, r.rule_type=$rule_type, r.pattern=$pattern,
                r.weight=$weight, r.applies_to=$applies_to, r.is_active=true, r.created_at=coalesce(r.created_at, $created_at)
            MERGE (b)-[:HAS_RULE]->(r)
            """,
            id=rule_id,
            bucket_name=bucket_name,
            rule_type=rule_type,
            pattern=pattern,
            weight=weight,
            applies_to=applies_to,
            created_at=now_iso(),
        )

    def upsert_item_bucket(self, item_id: str, bucket_name: str, confidence: float, evidence_json: str, assigned_by: str, assigned_at: str):
        self._execute_write(
            """
            MERGE (b:BucketDefinition {name: $bucket_name})
            ON CREATE SET b.id=$bucket_name, b.created_at=$assigned_at, b.bucket_type='system', b.is_active=true
            MATCH (i:Item {id: $item_id})
            MERGE (i)-[rel:IN_BUCKET]->(b)
            SET rel.confidence=$confidence, rel.evidence_json=$evidence_json, rel.assigned_by=$assigned_by, rel.assigned_at=$assigned_at
            """,
            item_id=item_id,
            bucket_name=bucket_name,
            confidence=confidence,
            evidence_json=evidence_json,
            assigned_by=assigned_by,
            assigned_at=assigned_at,
        )

    def get_item_row_by_path(self, path_or_url: str):
        rows = self._execute_read("MATCH (i:Item {path_or_url: $path_or_url}) RETURN i.id AS id, i.modified_time AS modified_time, i.size_bytes AS size_bytes", path_or_url=path_or_url)
        return rows[0] if rows else None

    def get_chunk_by_item_and_type(self, item_id: str, chunk_type: str):
        rows = self._execute_read("MATCH (:Item {id: $item_id})-[:HAS_CHUNK]->(c:Chunk {chunk_type: $chunk_type}) RETURN c.id AS id", item_id=item_id, chunk_type=chunk_type)
        return rows[0] if rows else None

    def fetch_items_for_bucket_assignment(self):
        return self._execute_read("MATCH (i:Item) RETURN i.id AS id, i.path_or_url AS path_or_url, i.filename AS filename, i.extension AS extension, i.metadata_json AS metadata_json")

    def search_chunks(self, query: str, bucket: str | None = None):
        if bucket:
            return self._execute_read(
                """
                CALL db.index.fulltext.queryNodes('chunkText', $query) YIELD node AS c
                MATCH (i:Item)-[:HAS_CHUNK]->(c)
                MATCH (i)-[:IN_BUCKET]->(:BucketDefinition {name: $bucket})
                RETURN i.path_or_url AS path_or_url, c.text AS text
                """,
                query=query,
                bucket=bucket,
            )
        return self._execute_read(
            """
            CALL db.index.fulltext.queryNodes('chunkText', $query) YIELD node AS c
            MATCH (i:Item)-[:HAS_CHUNK]->(c)
            RETURN i.path_or_url AS path_or_url, c.text AS text
            """,
            query=query,
        )

    def fetch_chunks_for_embedding(self):
        return self._execute_read("MATCH (c:Chunk) RETURN c.id AS id, c.text AS text")

    def fetch_semantic_search_rows(self, model: str):
        return self._execute_read(
            """
            MATCH (i:Item)-[:HAS_CHUNK]->(c:Chunk)-[:HAS_EMBEDDING]->(e:Embedding {model: $model})
            RETURN i.path_or_url AS path_or_url, c.text AS text, e.embedding_json AS embedding_json
            """,
            model=model,
        )

    def embedding_exists(self, chunk_id: str, model: str):
        rows = self._execute_read("MATCH (:Chunk {id: $chunk_id})-[:HAS_EMBEDDING]->(:Embedding {model: $model}) RETURN 1 AS exists", chunk_id=chunk_id, model=model)
        return bool(rows)

    def insert_embedding(self, embedding_id: str, chunk_id: str, model: str, embedding_json: str, dimensions: int):
        self._execute_write(
            """
            MATCH (c:Chunk {id: $chunk_id})
            MERGE (e:Embedding {id: $id})
            SET e.chunk_id=$chunk_id, e.model=$model, e.embedding_json=$embedding_json, e.dimensions=$dimensions, e.created_at=coalesce(e.created_at, $created_at)
            MERGE (c)-[:HAS_EMBEDDING]->(e)
            """,
            id=embedding_id,
            chunk_id=chunk_id,
            model=model,
            embedding_json=embedding_json,
            dimensions=dimensions,
            created_at=now_iso(),
        )

    def fetch_video_items(self):
        return self._execute_read("MATCH (i:Item {item_type: 'video'}) RETURN i.id AS id, i.path_or_url AS path_or_url")

    def insert_frame_ocr_chunk(self, chunk_id: str, item_id: str, text: str):
        props = {"id": chunk_id, "item_id": item_id, "chunk_type": "frame_ocr", "text": text, "timestamp_start": 5.0, "timestamp_end": 5.0, "metadata_json": "{}", "created_at": now_iso()}
        self._execute_write(
            """
            MATCH (i:Item {id: $item_id})
            MERGE (c:Chunk {id: $id})
            SET c += $props
            MERGE (i)-[:HAS_CHUNK]->(c)
            """,
            item_id=item_id,
            id=chunk_id,
            props=props,
        )

    def fetch_item_by_path_or_url(self, path_or_url: str):
        rows = self._execute_read("MATCH (i:Item {path_or_url: $path_or_url}) RETURN properties(i) AS props", path_or_url=path_or_url)
        return Row(rows[0]["props"]) if rows else None

    def fetch_item_bucket_explanations(self, path_or_url: str):
        return self._execute_read(
            """
            MATCH (:Item {path_or_url: $path_or_url})-[rel:IN_BUCKET]->(b:BucketDefinition)
            RETURN b.name AS bucket_name, rel.confidence AS confidence, rel.evidence_json AS evidence_json
            """,
            path_or_url=path_or_url,
        )

    def fetch_bucket_contents(self, bucket_name: str):
        return self._execute_read("MATCH (i:Item)-[:IN_BUCKET]->(:BucketDefinition {name: $bucket_name}) RETURN i.path_or_url AS path_or_url", bucket_name=bucket_name)

    def fetch_bucket_stats(self):
        return self._execute_read(
            """
            MATCH (:Item)-[:IN_BUCKET]->(b:BucketDefinition)
            RETURN b.name AS bucket_name, count(*) AS c
            ORDER BY c DESC
            """
        )


def _adapter(conn=None):
    return conn if conn is not None else connect_db()


def upsert_source(conn, source_id, root_path, label, config_json):
    _adapter(conn).upsert_source(source_id, root_path, label, config_json)


def upsert_item(conn, values: tuple):
    _adapter(conn).upsert_item(values)


def upsert_chunk(conn, values: tuple):
    _adapter(conn).upsert_chunk(values)


def insert_fts(conn, chunk_id: str, text: str):
    _adapter(conn).insert_fts(chunk_id, text)


def upsert_bucket_definition(conn, name: str, description: str, bucket_type: str):
    _adapter(conn).upsert_bucket_definition(name, description, bucket_type)


def insert_bucket_rule(conn, rule_id: str, bucket_name: str, rule_type: str, pattern: str, weight: float, applies_to: str):
    _adapter(conn).insert_bucket_rule(rule_id, bucket_name, rule_type, pattern, weight, applies_to)


def upsert_item_bucket(conn, item_id: str, bucket_name: str, confidence: float, evidence_json: str, assigned_by: str, assigned_at: str):
    _adapter(conn).upsert_item_bucket(item_id, bucket_name, confidence, evidence_json, assigned_by, assigned_at)


def get_item_row_by_path(conn, path_or_url: str):
    return _adapter(conn).get_item_row_by_path(path_or_url)


def get_chunk_by_item_and_type(conn, item_id: str, chunk_type: str):
    return _adapter(conn).get_chunk_by_item_and_type(item_id, chunk_type)


def upsert_bookmark_source(conn, source_id: str, bookmark_path: str, label: str, config_json: str):
    _adapter(conn).upsert_bookmark_source(source_id, bookmark_path, label, config_json)


def search_chunks(conn, query: str, bucket: str | None = None):
    return _adapter(conn).search_chunks(query, bucket)


def fetch_chunks_for_embedding(conn):
    return _adapter(conn).fetch_chunks_for_embedding()


def fetch_semantic_search_rows(conn, model: str):
    return _adapter(conn).fetch_semantic_search_rows(model)


def embedding_exists(conn, chunk_id: str, model: str):
    return _adapter(conn).embedding_exists(chunk_id, model)


def insert_embedding(conn, embedding_id: str, chunk_id: str, model: str, embedding_json: str, dimensions: int):
    _adapter(conn).insert_embedding(embedding_id, chunk_id, model, embedding_json, dimensions)


def fetch_video_items(conn):
    return _adapter(conn).fetch_video_items()


def insert_frame_ocr_chunk(conn, chunk_id: str, item_id: str, text: str):
    _adapter(conn).insert_frame_ocr_chunk(chunk_id, item_id, text)


def fetch_item_by_path_or_url(conn, path_or_url: str):
    return _adapter(conn).fetch_item_by_path_or_url(path_or_url)


def fetch_item_bucket_explanations(conn, path_or_url: str):
    return _adapter(conn).fetch_item_bucket_explanations(path_or_url)


def fetch_bucket_contents(conn, bucket_name: str):
    return _adapter(conn).fetch_bucket_contents(bucket_name)


def fetch_bucket_stats(conn):
    return _adapter(conn).fetch_bucket_stats()
