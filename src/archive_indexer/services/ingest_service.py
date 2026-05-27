from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config.settings import load_yaml
from ..adapters.db import connect_db, now_iso, upsert_source, upsert_item, upsert_chunk, insert_fts, get_item_row_by_path, get_chunk_by_item_and_type, upsert_bookmark_source
from ..core.parsers import BookmarkParser, extract_domain

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aiff", ".ogg", ".m4a", ".aac", ".mid", ".midi"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def hash_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_item(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "file"


def should_skip(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def load_sources(config_dir: Path) -> list[dict]:
    data = load_yaml(config_dir / "sources.yaml")
    sources = data.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("sources must be a list")
    return sources


def ingest_folders(db_path: Path, config_dir: Path, source_label: str | None = None) -> int:
    conn = connect_db(db_path)
    inserted = 0
    try:
        for source in load_sources(config_dir):
            if source.get("type") != "folder":
                continue
            if source_label and source.get("label") != source_label:
                continue
            root = Path(source["path"]).expanduser().resolve()
            source_id = source.get("id") or source.get("label") or str(root)
            upsert_source(conn, source_id, str(root), source.get("label"), json.dumps(source))
            for dirpath, _, filenames in os.walk(root):
                for name in filenames:
                    p = Path(dirpath) / name
                    if should_skip(p):
                        continue
                    stat = p.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                    existing = get_item_row_by_path(conn, str(p))
                    if existing and existing["modified_time"] == mtime and existing["size_bytes"] == stat.st_size:
                        continue
                    item_id = existing["id"] if existing else str(uuid.uuid4())
                    mime, _ = mimetypes.guess_type(str(p))
                    upsert_item(conn, (item_id, source_id, classify_item(p), str(p), p.name, p.suffix.lower(), mime, stat.st_size, mtime, hash_file(p), json.dumps({"parent": str(p.parent)}), now_iso()))
                    inserted += 1
                    create_basic_chunks(conn, item_id, p)
        conn.commit()
        return inserted
    finally:
        conn.close()


def create_basic_chunks(conn, item_id: str, path: Path) -> None:
    ext = path.suffix.lower()
    item_type = classify_item(path)
    chunks = [("path_metadata", f"PATH: {path}\nFILENAME: {path.name}\nEXTENSION: {ext}")]
    if item_type == "audio":
        chunks.append(("audio_metadata", f"TYPE: audio_metadata\nPATH: {path}\nEXTENSION: {ext}"))
    elif item_type == "video":
        chunks.append(("video_metadata", f"TYPE: video_metadata\nPATH: {path}\nEXTENSION: {ext}"))
    for chunk_type, text in chunks:
        existing = get_chunk_by_item_and_type(conn, item_id, chunk_type)
        chunk_id = existing["id"] if existing else str(uuid.uuid4())
        upsert_chunk(conn, (chunk_id, item_id, chunk_type, text, "{}", now_iso()))
        insert_fts(conn, chunk_id, text)


def ingest_bookmarks(db_path: Path, bookmark_file: Path) -> int:
    conn = connect_db(db_path)
    parser = BookmarkParser()
    parser.feed(bookmark_file.read_text(encoding="utf-8", errors="ignore"))
    source_id = f"bookmark:{bookmark_file}"
    upsert_bookmark_source(conn, source_id, str(bookmark_file), bookmark_file.name, "{}")
    count = 0
    for bm in parser.items:
        item_id = str(uuid.uuid4())
        domain = extract_domain(bm["url"])
        upsert_item(conn, (item_id, source_id, "bookmark", bm["url"], bm["title"], "", "", 0, "", "", json.dumps({"domain": domain, "folder": bm["folder"]}), now_iso()))
        chunk_id = str(uuid.uuid4())
        text = f"TITLE: {bm['title']}\nURL: {bm['url']}\nDOMAIN: {domain}\nFOLDER: {bm['folder']}"
        upsert_chunk(conn, (chunk_id, item_id, "bookmark_metadata", text, "{}", now_iso()))
        insert_fts(conn, chunk_id, text)
        count += 1
    conn.commit()
    conn.close()
    return count
