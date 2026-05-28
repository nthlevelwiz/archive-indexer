from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from ..core.parsers import mini_yaml_parse
from ..adapters.db import connect_db, now_iso, upsert_bucket_definition, insert_bucket_rule, upsert_item_bucket


def assign_buckets(db_path: Path, config_dir: Path) -> int:
    data = mini_yaml_parse((config_dir / "buckets.yaml").read_text(encoding="utf-8"))
    buckets = data.get("buckets", [])
    conn = connect_db(db_path)
    assigned = 0
    try:
        for b in buckets:
            bname = b["name"]
            upsert_bucket_definition(conn, bname, b.get("description", ""), b.get("type", "topic"))
            for r in b.get("rules", []):
                insert_bucket_rule(
                    conn,
                    str(uuid.uuid4()),
                    bname,
                    r.get("type", "text_regex"),
                    r.get("pattern", ".*"),
                    float(r.get("weight", 1.0)),
                    r.get("applies_to", "text"),
                )

        # todo: move to db wrapper
        items = conn.execute("SELECT id, path_or_url, filename, extension, metadata_json FROM items").fetchall()
        for it in items:
            text = " ".join([it["path_or_url"] or "", it["filename"] or "", it["extension"] or "", it["metadata_json"] or ""])
            matched = False
            for b in buckets:
                score = 0.0
                evidence: list[dict[str, float | str]] = []
                for r in b.get("rules", []):
                    if re.search(r.get("pattern", ""), text, re.IGNORECASE):
                        w = float(r.get("weight", 1.0))
                        score += w
                        evidence.append({"pattern": r.get("pattern", ""), "weight": w})
                if score > 0:
                    matched = True
                    conf = min(score / float(b.get("threshold", 1.0)), 1.0)
                    upsert_item_bucket(conn, it["id"], b["name"], conf, json.dumps(evidence), "rules", now_iso())
                    assigned += 1
            if not matched:
                upsert_item_bucket(conn, it["id"], "review_later", 0.1, "[]", "fallback", now_iso())
                assigned += 1

        conn.commit()
        return assigned
    finally:
        conn.close()
