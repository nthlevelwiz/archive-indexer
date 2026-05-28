from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  root_path_or_file TEXT NOT NULL,
  label TEXT,
  config_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  item_type TEXT NOT NULL,
  path_or_url TEXT NOT NULL UNIQUE,
  filename TEXT,
  extension TEXT,
  mime_type TEXT,
  size_bytes INTEGER,
  modified_time TEXT,
  content_hash TEXT,
  metadata_json TEXT,
  indexed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL,
  chunk_type TEXT NOT NULL,
  text TEXT NOT NULL,
  timestamp_start REAL,
  timestamp_end REAL,
  metadata_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bucket_definitions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  bucket_type TEXT,
  is_active INTEGER DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bucket_rules (
  id TEXT PRIMARY KEY,
  bucket_name TEXT NOT NULL,
  rule_type TEXT NOT NULL,
  pattern TEXT NOT NULL,
  weight REAL DEFAULT 1.0,
  applies_to TEXT,
  is_active INTEGER DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item_buckets (
  item_id TEXT NOT NULL,
  bucket_name TEXT NOT NULL,
  confidence REAL NOT NULL,
  evidence_json TEXT,
  assigned_by TEXT NOT NULL,
  assigned_at TEXT NOT NULL,
  PRIMARY KEY (item_id, bucket_name)
);

CREATE TABLE IF NOT EXISTS embeddings (
  id TEXT PRIMARY KEY,
  chunk_id TEXT NOT NULL,
  model TEXT NOT NULL,
  embedding_json TEXT NOT NULL,
  dimensions INTEGER,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
  chunk_id UNINDEXED,
  text
);

CREATE INDEX IF NOT EXISTS idx_items_source_id ON items(source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_item_id ON chunks(item_id);
CREATE INDEX IF NOT EXISTS idx_bucket_rules_bucket_name ON bucket_rules(bucket_name);
CREATE INDEX IF NOT EXISTS idx_item_buckets_item_id ON item_buckets(item_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_chunk_model ON embeddings(chunk_id, model);
"""

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # return conn
    # we should be using the singleton class instance


def init_db(db_path: str | Path) -> None:
    conn = connect_db(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


class DatabaseAdapter:
    def __init__(self, conn: sqlite3.Connection):
        if not hasattr(self, "conn"): self.conn = conn
    
    def upsert_source(self, source_id, root_path, label, config_json):
        self.conn.execute("INSERT OR REPLACE INTO sources(id, source_type, root_path_or_file, label, config_json, created_at) VALUES (?, 'folder', ?, ?, ?, ?)", (source_id, root_path, label, config_json, now_iso()))

    def upsert_item(self, values: tuple):
        self.conn.execute("""INSERT OR REPLACE INTO items(
            id, source_id, item_type, path_or_url, filename, extension, mime_type, size_bytes,
            modified_time, content_hash, metadata_json, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", values)

    def upsert_chunk(self, values: tuple):
        self.conn.execute("INSERT OR REPLACE INTO chunks(id, item_id, chunk_type, text, timestamp_start, timestamp_end, metadata_json, created_at) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)", values)

    def insert_fts(self, chunk_id: str, text: str):
        self.conn.execute("INSERT INTO chunk_fts(chunk_id, text) VALUES (?, ?)", (chunk_id, text))

    def upsert_bucket_definition(self, name: str, description: str, bucket_type: str):
        self.conn.execute("INSERT OR REPLACE INTO bucket_definitions(id, name, description, bucket_type, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)", (name, name, description, bucket_type, now_iso()))

    def insert_bucket_rule(self, rule_id: str, bucket_name: str, rule_type: str, pattern: str, weight: float, applies_to: str):
        self.conn.execute("INSERT INTO bucket_rules(id, bucket_name, rule_type, pattern, weight, applies_to, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)", (rule_id, bucket_name, rule_type, pattern, weight, applies_to, now_iso()))

    def upsert_item_bucket(self, item_id: str, bucket_name: str, confidence: float, evidence_json: str, assigned_by: str, assigned_at: str):
        self.conn.execute("INSERT OR REPLACE INTO item_buckets(item_id, bucket_name, confidence, evidence_json, assigned_by, assigned_at) VALUES (?, ?, ?, ?, ?, ?)", (item_id, bucket_name, confidence, evidence_json, assigned_by, assigned_at))

    def get_item_row_by_path(self, path_or_url: str):
        return self.conn.execute("SELECT id, modified_time, size_bytes FROM items WHERE path_or_url = ?", (path_or_url,)).fetchone()

    def get_chunk_by_item_and_type(self, item_id: str, chunk_type: str):
        return self.conn.execute("SELECT id FROM chunks WHERE item_id = ? AND chunk_type = ?", (item_id, chunk_type)).fetchone()

    def upsert_bookmark_source(self, source_id: str, bookmark_path: str, label: str, config_json: str):
        self.conn.execute(
            "INSERT OR REPLACE INTO sources(id, source_type, root_path_or_file, label, config_json, created_at) VALUES (?, 'bookmark_html', ?, ?, ?, ?)",
            (source_id, bookmark_path, label, config_json, now_iso()),
        )

    def search_chunks(self, query: str, bucket: str | None = None):
        sql = """SELECT i.path_or_url, c.text FROM chunk_fts f JOIN chunks c ON c.id=f.chunk_id JOIN items i ON i.id=c.item_id """
        params: list[str] = []
        if bucket:
            sql += "JOIN item_buckets ib ON ib.item_id=i.id WHERE ib.bucket_name=? AND f.text MATCH ?"
            params = [bucket, query]
        else:
            sql += "WHERE f.text MATCH ?"
            params = [query]
        return self.conn.execute(sql, params).fetchall()

    def fetch_chunks_for_embedding(self):
        return self.conn.execute("SELECT id, text FROM chunks").fetchall()

    def fetch_semantic_search_rows(self, model: str):
        return self.conn.execute(
            """
            SELECT i.path_or_url, c.text, e.embedding_json
            FROM embeddings e
            JOIN chunks c ON c.id=e.chunk_id
            JOIN items i ON i.id=c.item_id
            WHERE e.model=?
            """,
            (model,),
        ).fetchall()

    def embedding_exists(self, chunk_id: str, model: str):
        return self.conn.execute("SELECT 1 FROM embeddings WHERE chunk_id=? AND model=?", (chunk_id, model)).fetchone() is not None

    def insert_embedding(self, embedding_id: str, chunk_id: str, model: str, embedding_json: str, dimensions: int):
        self.conn.execute(
            "INSERT INTO embeddings(id, chunk_id, model, embedding_json, dimensions, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (embedding_id, chunk_id, model, embedding_json, dimensions),
        )

    def fetch_video_items(self):
        return self.conn.execute("SELECT id, path_or_url FROM items WHERE item_type='video'").fetchall()

    def insert_frame_ocr_chunk(self, chunk_id: str, item_id: str, text: str):
        self.conn.execute(
            "INSERT INTO chunks(id, item_id, chunk_type, text, timestamp_start, timestamp_end, metadata_json, created_at) VALUES (?, ?, 'frame_ocr', ?, 5.0, 5.0, '{}', datetime('now'))",
            (chunk_id, item_id, text),
        )
        self.conn.execute("INSERT INTO chunk_fts(chunk_id, text) VALUES (?, ?)", (chunk_id, text))

    def fetch_item_by_path_or_url(self, path_or_url: str):
        return self.conn.execute("SELECT * FROM items WHERE path_or_url=?", (path_or_url,)).fetchone()

    def fetch_item_bucket_explanations(self, path_or_url: str):
        return self.conn.execute(
            "SELECT bucket_name, confidence, evidence_json FROM item_buckets ib JOIN items i ON i.id=ib.item_id WHERE i.path_or_url=?",
            (path_or_url,),
        ).fetchall()

    def fetch_bucket_contents(self, bucket_name: str):
        return self.conn.execute(
            "SELECT i.path_or_url FROM item_buckets ib JOIN items i ON i.id=ib.item_id WHERE ib.bucket_name=?",
            (bucket_name,),
        ).fetchall()

    def fetch_bucket_stats(self):
        return self.conn.execute(
            "SELECT bucket_name, COUNT(*) AS c FROM item_buckets GROUP BY bucket_name ORDER BY c DESC"
        ).fetchall()


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
