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
    return conn


def init_db(db_path: str | Path) -> None:
    conn = connect_db(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def upsert_source(conn, source_id, root_path, label, config_json):
    conn.execute("INSERT OR REPLACE INTO sources(id, source_type, root_path_or_file, label, config_json, created_at) VALUES (?, 'folder', ?, ?, ?, ?)", (source_id, root_path, label, config_json, now_iso()))


def upsert_item(conn, values: tuple):
    conn.execute("""INSERT OR REPLACE INTO items(
        id, source_id, item_type, path_or_url, filename, extension, mime_type, size_bytes,
        modified_time, content_hash, metadata_json, indexed_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", values)


def upsert_chunk(conn, values: tuple):
    conn.execute("INSERT OR REPLACE INTO chunks(id, item_id, chunk_type, text, timestamp_start, timestamp_end, metadata_json, created_at) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)", values)


def insert_fts(conn, chunk_id: str, text: str):
    conn.execute("INSERT INTO chunk_fts(chunk_id, text) VALUES (?, ?)", (chunk_id, text))


def upsert_bucket_definition(conn, name: str, description: str, bucket_type: str):
    conn.execute("INSERT OR REPLACE INTO bucket_definitions(id, name, description, bucket_type, is_active, created_at) VALUES (?, ?, ?, ?, 1, ?)", (name, name, description, bucket_type, now_iso()))


def insert_bucket_rule(conn, rule_id: str, bucket_name: str, rule_type: str, pattern: str, weight: float, applies_to: str):
    conn.execute("INSERT INTO bucket_rules(id, bucket_name, rule_type, pattern, weight, applies_to, is_active, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?)", (rule_id, bucket_name, rule_type, pattern, weight, applies_to, now_iso()))


def upsert_item_bucket(conn, item_id: str, bucket_name: str, confidence: float, evidence_json: str, assigned_by: str, assigned_at: str):
    conn.execute("INSERT OR REPLACE INTO item_buckets(item_id, bucket_name, confidence, evidence_json, assigned_by, assigned_at) VALUES (?, ?, ?, ?, ?, ?)", (item_id, bucket_name, confidence, evidence_json, assigned_by, assigned_at))


def get_item_row_by_path(conn, path_or_url: str):
    return conn.execute("SELECT id, modified_time, size_bytes FROM items WHERE path_or_url = ?", (path_or_url,)).fetchone()


def get_chunk_by_item_and_type(conn, item_id: str, chunk_type: str):
    return conn.execute("SELECT id FROM chunks WHERE item_id = ? AND chunk_type = ?", (item_id, chunk_type)).fetchone()


def upsert_bookmark_source(conn, source_id: str, bookmark_path: str, label: str, config_json: str):
    conn.execute(
        "INSERT OR REPLACE INTO sources(id, source_type, root_path_or_file, label, config_json, created_at) VALUES (?, 'bookmark_html', ?, ?, ?, ?)",
        (source_id, bookmark_path, label, config_json, now_iso()),
    )
