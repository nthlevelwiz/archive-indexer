from __future__ import annotations

import argparse
import json
import logging
import uuid
from pathlib import Path

from archive_indexer.adapters.db import (
    connect_db,
    embedding_exists,
    fetch_bucket_contents,
    fetch_bucket_stats,
    fetch_chunks_for_embedding,
    fetch_item_bucket_explanations,
    fetch_item_by_path_or_url,
    fetch_video_items,
    init_db,
    insert_embedding,
    insert_frame_ocr_chunk,
    search_chunks,
)
from archive_indexer.adapters.embedding import embed_text
from archive_indexer.adapters.ocr import extract_frame_ocr_text
from archive_indexer.services.bucket_service import assign_buckets
from archive_indexer.services.ingest_service import ingest_bookmarks, ingest_folders

init_db_command_arg = "init-db"
ingest_command_arg = "ingest"
ingest_bookmarks_command_arg = "ingest-bookmarks"
assign_buckets_command_arg = "assign-buckets"
search_command_arg = "search"
embed_command_arg = "embed"
ocr_videos_command_arg = "ocr-videos"
show_item_command_arg = "show-item"
explain_buckets_command_arg = "explain-buckets"
list_bucket_command_arg = "list-bucket"
list_bucket_contents_command_arg = "list-bucket-contents"
bucket_stats_command_arg = "bucket-stats"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive_indexer", description="Archive Indexer CLI")
    parser.add_argument("--data-dir", default="data", help="Directory for SQLite database")
    parser.add_argument("--config-dir", default="config", help="Directory for config YAML files")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(init_db_command_arg, help="Initialize SQLite schema")

    p_ingest = subparsers.add_parser(ingest_command_arg, help="Ingest folder sources")
    p_ingest.add_argument("--source", default=None)

    p_bm = subparsers.add_parser(ingest_bookmarks_command_arg, help="Ingest bookmark html")
    p_bm.add_argument("path")

    subparsers.add_parser(assign_buckets_command_arg)

    p_search = subparsers.add_parser(search_command_arg)
    p_search.add_argument("query")
    p_search.add_argument("--bucket", default=None)
    p_search.add_argument("--semantic", action="store_true")

    subparsers.add_parser(embed_command_arg)
    subparsers.add_parser(ocr_videos_command_arg)

    p_show = subparsers.add_parser(show_item_command_arg)
    p_show.add_argument("path_or_url")

    p_explain = subparsers.add_parser(explain_buckets_command_arg)
    p_explain.add_argument("path_or_url")

    p_list = subparsers.add_parser(list_bucket_contents_command_arg)
    p_list.add_argument("bucket_name")

    p_list_alias = subparsers.add_parser(list_bucket_command_arg)
    p_list_alias.add_argument("bucket_name")

    subparsers.add_parser(bucket_stats_command_arg)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = Path(args.data_dir) / "archive_index.sqlite"
    config_dir = Path(args.config_dir)

    if args.command == init_db_command_arg:
        init_db(db_path)
        logging.info("Initialized database at %s", db_path)
        return 0
    if args.command == ingest_command_arg:
        n = ingest_folders(db_path, config_dir, args.source)
        print(f"ingested {n} items")
        return 0
    if args.command == ingest_bookmarks_command_arg:
        n = ingest_bookmarks(db_path, Path(args.path))
        print(f"ingested {n} bookmarks")
        return 0
    if args.command == assign_buckets_command_arg:
        n = assign_buckets(db_path, config_dir)
        print(f"assigned {n} bucket rows")
        return 0

    conn = connect_db(db_path)
    try:
        if args.command == search_command_arg:
            for r in search_chunks(conn, args.query, args.bucket):
                print(f"{r['path_or_url']}\n{r['text'][:120]}")
            return 0

        if args.command == embed_command_arg:
            model = "local-hash-v1"
            rows = fetch_chunks_for_embedding(conn)
            for r in rows:
                if embedding_exists(conn, r["id"], model):
                    continue
                emb = embed_text(r["text"])
                insert_embedding(conn, str(uuid.uuid4()), r["id"], model, json.dumps(emb), len(emb))
            conn.commit()
            print("embedded")
            return 0

        if args.command == ocr_videos_command_arg:
            rows = fetch_video_items(conn)
            for r in rows:
                txt = extract_frame_ocr_text(r["path_or_url"], second=5)
                cid = str(uuid.uuid4())
                insert_frame_ocr_chunk(conn, cid, r["id"], txt)
            conn.commit()
            print("ocr complete")
            return 0

        if args.command == show_item_command_arg:
            print(dict(fetch_item_by_path_or_url(conn, args.path_or_url) or {}))
            return 0

        if args.command == explain_buckets_command_arg:
            for r in fetch_item_bucket_explanations(conn, args.path_or_url):
                print(dict(r))
            return 0

        if args.command in {list_bucket_command_arg, list_bucket_contents_command_arg}:
            for r in fetch_bucket_contents(conn, args.bucket_name):
                print(r["path_or_url"])
            return 0

        if args.command == bucket_stats_command_arg:
            for r in fetch_bucket_stats(conn):
                print(f"{r['bucket_name']}\t{r['c']}")
            return 0
    finally:
        conn.close()

    parser.print_help()
    return 0
