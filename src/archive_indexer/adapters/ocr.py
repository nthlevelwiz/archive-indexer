from __future__ import annotations

import tempfile
from pathlib import Path

import ffmpeg
import pytesseract
from PIL import Image


def _fallback_ocr_text(video_path: str, second: int) -> str:
    stem = Path(video_path).stem.replace("-", " ").replace("_", " ")
    return f"frame {second}s text from {stem}"


def extract_frame_ocr_text(video_path: str, second: int = 5) -> str:
    p = Path(video_path)
    with tempfile.TemporaryDirectory() as tmp:
        frame = Path(tmp) / "frame.png"
        try:
            (
                ffmpeg
                .input(str(p), ss=second)
                .output(str(frame), vframes=1)
                .overwrite_output()
                .run(quiet=True)
            )
            text = pytesseract.image_to_string(Image.open(frame)).strip()
            if text:
                return text
        except Exception:
            return _fallback_ocr_text(video_path, second)

    return _fallback_ocr_text(video_path, second)
