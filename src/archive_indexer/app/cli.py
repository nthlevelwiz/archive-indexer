from __future__ import annotations

import argparse
import json
import uuid
import logging
from pathlib import Path

from archive_indexer.adapters.db import connect_db, init_db, search_db
#todo: rename change db adapter naming scheme from "verb_db" to just "verb"
todo: move the sql queries into the adapter. keep this file as minimal as possible. 
#todo: move search, embed, ocr-videos, show items, explain bucke
from archive_indexer.adapters.embedding import cosine_similarity, embed_text
from archive_indexer.adapters.ocr import extract_frame_ocr_text
from archive_indexer.services.bucket_service import assign_buckets
from archive_indexer.services.ingest_service import ingest_bookmarks, ingest_folders
# todo: use variables instead of strings for parser args in cases when args.command needs to check for equality
# example: 
search_command_arg = "search"
embed_command_arg = "embed"
todo:ocr videos, show item, list bucket contents, bucket stats

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive_indexer", description="Archive Indexer CLI")

    # sql, config directory settings 
    parser.add_argument("--data-dir", default="data", help="Directory for SQLite database")
    parser.add_argument("--config-dir", default="config", help="Directory for config YAML files")

    # init db
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init-db", help="Initialize SQLite schema")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest folder sources")
    p_ingest.add_argument("--source", default=None)

    # bookmarks html files will be in the ingest directory
    # p_bm = subparsers.add_parser("ingest-bookmarks", help="Ingest bookmark html")
    # p_bm.add_argument("path")
    
    # assign buckets 
    subparsers.add_parser("assign-buckets")

    # search
    p_search = subparsers.add_parser(search_command_arg) #see above
    p_search.add_argument("query")
    p_search.add_argument("--bucket", default=None)
    p_search.add_argument("--semantic", action="store_true")

    # embed
    subparsers.add_parser("embed")
    subparsers.add_parser("ocr-videos")

    # todo: unclear what an "item" is. 
    p_show = subparsers.add_parser("show-item")
    p_show.add_argument("path_or_url")

    #explain buckets
    p_explain = subparsers.add_parser("explain-buckets")
    p_explain.add_argument("path_or_url")

    #list bucket contents
    p_list = subparsers.add_parser("list-bucket-contents")
    p_list.add_argument("bucket_name")

    #bucket stats
    subparsers.add_parser("bucket-stats")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = Path(args.data_dir) / "archive_index.sqlite"
    config_dir = Path(args.config_dir)

    if args.command == "init-db":
        init_db(db_path)
        logging.info("Initialized database at %s", db_path)
        return 0
    if args.command == "ingest":
        n = ingest_folders(db_path, config_dir, args.source)
        print(f"ingested {n} items")
        return 0
    # see above
    # if args.command == "ingest-bookmarks":
    #     n = ingest_bookmarks(db_path, Path(args.path))
    #     print(f"ingested {n} bookmarks")
    #     return 0
    if args.command == "assign-buckets":
        n = assign_buckets(db_path, config_dir)
        print(f"assigned {n} bucket rows")
        return 0
    conn = connect_db(db_path)
    try:
        if args.command == search_command_arg:
            sql = """SELECT i.path_or_url, c.text FROM chunk_fts f JOIN chunks c ON c.id=f.chunk_id JOIN items i ON i.id=c.item_id """
            params = []
            if args.bucket:
                sql += "JOIN item_buckets ib ON ib.item_id=i.id WHERE ib.bucket_name=? AND f.text MATCH ?"
                params = [args.bucket, args.query]
            else:
                sql += "WHERE f.text MATCH ?"
                params = [args.query]
            for r in conn.execute(sql, params).fetchall():
                print(f"{r['path_or_url']}\n{r['text'][:120]}")
            return 0
        # todo: use variables instead of strings for parser args in cases when args.command needs to check for equality

        if args.command == "embed":
            model = "local-hash-v1"
            rows = conn.execute("SELECT id, text FROM chunks").fetchall()
            for r in rows:
                exists = conn.execute("SELECT 1 FROM embeddings WHERE chunk_id=? AND model=?", (r["id"], model)).fetchone()
                if exists:
                    continue
                emb = embed_text(r["text"])
                conn.execute("INSERT INTO embeddings(id, chunk_id, model, embedding_json, dimensions, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))", (str(uuid.uuid4()), r["id"], model, json.dumps(emb), len(emb)))
            conn.commit(); print("embedded") ; return 0
        # todo: use variables instead of strings for parser args in cases when args.command needs to check for equality

        if args.command == "ocr-videos":
            rows = conn.execute("SELECT id, path_or_url FROM items WHERE item_type='video'").fetchall()
            for r in rows:
                txt = extract_frame_ocr_text(r["path_or_url"], second=5)
                cid = str(uuid.uuid4())
                conn.execute("INSERT INTO chunks(id, item_id, chunk_type, text, timestamp_start, timestamp_end, metadata_json, created_at) VALUES (?, ?, 'frame_ocr', ?, 5.0, 5.0, '{}', datetime('now'))", (cid, r["id"], txt))
                conn.execute("INSERT INTO chunk_fts(chunk_id, text) VALUES (?, ?)", (cid, txt))
            conn.commit(); print("ocr complete"); return 0
        # todo: use variables instead of strings for parser args in cases when args.command needs to check for equality

        if args.command == "show-item":
            print(dict(conn.execute("SELECT * FROM items WHERE path_or_url=?", (args.path_or_url,)).fetchone() or {})); return 0
        # todo: use variables instead of strings for parser args in cases when args.command needs to check for equality

        if args.command == "explain-buckets":
            for r in conn.execute("SELECT bucket_name, confidence, evidence_json FROM item_buckets ib JOIN items i ON i.id=ib.item_id WHERE i.path_or_url=?", (args.path_or_url,)).fetchall():
                print(dict(r)); return 0
        # todo: use variables instead of strings for parser args in cases when args.command needs to check for equality

        if args.command == "list-bucket-contents":
            todo: see above cha
            for r in conn.execute("SELECT i.path_or_url FROM item_buckets ib JOIN items i ON i.id=ib.item_id WHERE ib.bucket_name=?", (args.bucket_name,)).fetchall():
                print(r["path_or_url"])
            return 0
        # todo: use variables instead of strings for parser args in cases when args.command needs to check for equality

        if args.command == "bucket-stats":
            for r in conn.execute("SELECT bucket_name, COUNT(*) AS c FROM item_buckets GROUP BY bucket_name ORDER BY c DESC").fetchall():
                print(f"{r['bucket_name']}\t{r['c']}")
            return 0
    finally:
        conn.close()
    parser.print_help()
    return 0
