from __future__ import annotations

import tempfile
from pathlib import Path

import ffmpeg
import pytesseract
from PIL import Image


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
        except Exception as exc:
            raise RuntimeError(f"OCR extraction failed for '{video_path}' at {second}s") from exc

    raise RuntimeError(f"OCR produced empty text for '{video_path}' at {second}s")
