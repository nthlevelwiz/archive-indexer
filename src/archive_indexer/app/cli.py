from __future__ import annotations

import argparse
import json
import logging
import uuid
from pathlib import Path

from archive_indexer.adapters.blarify import (
    DEFAULT_BLARIFY_EXTENSIONS_TO_SKIP,
    DEFAULT_BLARIFY_NAMES_TO_SKIP,
    blarify_neo4j_config_from_env,
    BlarifyNotInstalledError,
    build_blarify_graph_in_neo4j,
)
from archive_indexer.adapters.db import DatabaseAdapter, init_db, set_data_dir, set_neo4j_config
from archive_indexer.adapters.embedding import embed_text as embedding_adapter_embed_text
from archive_indexer.adapters.embedding import cosine_similarity
from archive_indexer.adapters.ocr import extract_frame_ocr_text as ocr_adapter_extract_frame_ocr_text
from archive_indexer.services.bucket_service import assign_buckets as bucket_service_assign_buckets
from archive_indexer.services.ingest_service import ingest_bookmarks as ingest_service_ingest_bookmarks, ingest_folders as ingest_service_ingest_folders


STR_INIT_DB_COMMAND_ARG = "init-db"
# todo: use all caps and prefix STR_ for arg variables, use above example
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
visualize_code_command_arg = "visualize-code"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive_indexer", description="Archive Indexer CLI")
    parser.add_argument("--data-dir", default="data", help="Deprecated; Neo4j is configured with --neo4j-* or NEO4J_* variables")
    parser.add_argument("--neo4j-uri", default=None, help="Neo4j URI, for example bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default=None, help="Neo4j username")
    parser.add_argument("--neo4j-password", default=None, help="Neo4j password")
    parser.add_argument("--neo4j-database", default=None, help="Neo4j database name")
    parser.add_argument("--config-dir", default="config", help="Directory for config YAML files")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(STR_INIT_DB_COMMAND_ARG, help="Initialize Neo4j constraints and indexes")

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

    p_visualize = subparsers.add_parser(
        visualize_code_command_arg, help="Build a Blarify code graph and save it to Neo4j"
    )
    p_visualize.add_argument("--root", default=".", help="Repository root to visualize")
    p_visualize.add_argument("--repo-id", default=None, help="Blarify repository identifier")
    p_visualize.add_argument("--entity-id", default=None, help="Blarify entity/organization identifier")
    p_visualize.add_argument(
        "--extensions-to-skip",
        action="append",
        default=None,
        help=f"Comma-separated extensions to skip (default: {', '.join(DEFAULT_BLARIFY_EXTENSIONS_TO_SKIP)})",
    )
    p_visualize.add_argument(
        "--names-to-skip",
        action="append",
        default=None,
        help=f"Comma-separated file or directory names to skip (default: {', '.join(DEFAULT_BLARIFY_NAMES_TO_SKIP)})",
    )
    p_visualize.add_argument("--generate-embeddings", action="store_true", help="Ask Blarify to generate embeddings")
    p_visualize.add_argument("--create-workflows", action="store_true", help="Ask Blarify to discover execution workflows")
    p_visualize.add_argument("--create-documentation", action="store_true", help="Ask Blarify to generate documentation nodes")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    set_data_dir(args.data_dir)
    set_neo4j_config(args.neo4j_uri, args.neo4j_user, args.neo4j_password, args.neo4j_database)
    config_dir = Path(args.config_dir)

    if args.command == STR_INIT_DB_COMMAND_ARG:
        init_db()
        logging.info("Initialized database")
        return 0
    if args.command == ingest_command_arg:
        n = ingest_service_ingest_folders(config_dir=config_dir, source_label=args.source)
        print(f"ingested {n} items")
        return 0
    if args.command == ingest_bookmarks_command_arg:
        n = ingest_service_ingest_bookmarks(bookmark_file=Path(args.path))
        print(f"ingested {n} bookmarks")
        return 0
    if args.command == assign_buckets_command_arg:
        n = bucket_service_assign_buckets(config_dir=config_dir)
        print(f"assigned {n} bucket rows")
        return 0
    if args.command == visualize_code_command_arg:
        config = blarify_neo4j_config_from_env(
            uri=args.neo4j_uri,
            user=args.neo4j_user,
            password=args.neo4j_password,
            database=args.neo4j_database,
            repo_id=args.repo_id,
            entity_id=args.entity_id,
        )
        try:
            result = build_blarify_graph_in_neo4j(
                root_path=args.root,
                config=config,
                extensions_to_skip=args.extensions_to_skip,
                names_to_skip=args.names_to_skip,
                generate_embeddings=args.generate_embeddings,
                create_workflows=args.create_workflows,
                create_documentation=args.create_documentation,
            )
        except BlarifyNotInstalledError as exc:
            logging.error("%s", exc)
            return 1
        print(
            "saved Blarify code graph to Neo4j: "
            f"{result.node_count} nodes, {result.relationship_count} relationships"
        )
        return 0

    db_adapter = DatabaseAdapter()
    try:
        if args.command == search_command_arg:
            if not args.semantic:
                for r in db_adapter.search_chunks(args.query, args.bucket):
                    print(f"{r['path_or_url']}\n{r['text'][:120]}")
                return 0

            qvec = embedding_adapter_embed_text(args.query, model="nomic-embed-text")
            rows = db_adapter.fetch_semantic_search_rows("nomic-embed-text")
            scored: list[tuple[float, str, str]] = []
            for r in rows:
                emb = json.loads(r["embedding_json"])
                if not isinstance(emb, list):
                    continue
                score = cosine_similarity(qvec, [float(x) for x in emb])
                scored.append((score, r["path_or_url"], r["text"]))
            scored.sort(key=lambda x: x[0], reverse=True)
            for score, path_or_url, text in scored[:5]:
                print(f"{score:.4f}\t{path_or_url}\n{text[:120]}")
            return 0

        if args.command == embed_command_arg:
            model = "nomic-embed-text"
            rows = db_adapter.fetch_chunks_for_embedding()
            for r in rows:
                row_id = r["id"]
                if db_adapter.embedding_exists(row_id, model):
                    continue
                emb = embedding_adapter_embed_text(r["text"])
                embedding_length = len(emb)
                json_serialized = json.dumps(emb)
                db_adapter.insert_embedding(str(uuid.uuid4()), row_id, model, json_serialized, embedding_length)
            db_adapter.commit()
            print("embedded")
            return 0

        if args.command == ocr_videos_command_arg:
            rows = db_adapter.fetch_video_items()
            for r in rows:
                txt = ocr_adapter_extract_frame_ocr_text(r["path_or_url"], second=5)
                cid = str(uuid.uuid4())
                db_adapter.insert_frame_ocr_chunk(cid, r["id"], txt)
            db_adapter.commit()
            print("ocr complete")
            return 0

        if args.command == show_item_command_arg:
            print(dict(db_adapter.fetch_item_by_path_or_url(args.path_or_url) or {}))
            return 0

        if args.command == explain_buckets_command_arg:
            for r in db_adapter.fetch_item_bucket_explanations(args.path_or_url):
                print(dict(r))
            return 0

        if args.command in {list_bucket_command_arg, list_bucket_contents_command_arg}:
            for r in db_adapter.fetch_bucket_contents(args.bucket_name):
                print(r["path_or_url"])
            return 0

        if args.command == bucket_stats_command_arg:
            for r in db_adapter.fetch_bucket_stats():
                print(f"{r['bucket_name']}\t{r['c']}")
            return 0
    finally:
        db_adapter.close()

    parser.print_help()
    return 0
