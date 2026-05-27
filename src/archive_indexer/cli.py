from __future__ import annotations

import argparse
import logging
from pathlib import Path

from archive_indexer.db import init_db


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archive_indexer", description="Archive Indexer CLI")
    parser.add_argument("--data-dir", default="data", help="Directory for SQLite database")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init-db", help="Initialize SQLite schema")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-db":
        db_path = Path(args.data_dir) / "archive_index.sqlite"
        init_db(db_path)
        logging.info("Initialized database at %s", db_path)
        return 0

    parser.print_help()
    return 0
