from __future__ import annotations

import sqlite3
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
