import hashlib
from pathlib import Path

from archive_indexer.services.ingest_service import classify_item, hash_file, should_skip


def test_classify_item_audio_video_and_file(tmp_path: Path):
    assert classify_item(tmp_path / "a.wav") == "audio"
    assert classify_item(tmp_path / "b.mp4") == "video"
    assert classify_item(tmp_path / "c.txt") == "file"


def test_should_skip_hidden_path(tmp_path: Path):
    assert should_skip(tmp_path / ".hidden" / "a.txt") is True
    assert should_skip(tmp_path / "visible" / "a.txt") is False


def test_hash_file_sha1(tmp_path: Path):
    p = tmp_path / "f.txt"
    p.write_text("abc")
    assert hash_file(p) == hashlib.sha1(b"abc").hexdigest()
