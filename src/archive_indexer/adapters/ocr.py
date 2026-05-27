from __future__ import annotations

from pathlib import Path


def extract_frame_ocr_text(video_path: str, second: int = 5) -> str:
    p = Path(video_path)
    stem = p.stem.replace("_", " ").replace("-", " ")
    return f"frame {second}s text from {stem}".strip()
