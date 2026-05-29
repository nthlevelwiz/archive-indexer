print("running tests/unit/test_phase0_cli.py")
import json
import os
from pathlib import Path
import subprocess

import pytest

from archive_indexer.adapters import db as db_mod
from archive_indexer.app import cli

ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
GEN = ROOT / "scripts" / "generate_fake_inputs.py"
GENERATED = ROOT / "sample_data" / "generated"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_cli_help_lists_init_db_command():
    print("executing command: python -m archive_indexer --help")
    result = subprocess.run(
        ["python", "-m", "archive_indexer", "--help"],
        check=True,
        capture_output=True,
        text=True,
        env=ENV,
    )
    assert "init-db" in result.stdout
    assert "--data-dir" in result.stdout


def test_cli_commands_with_generated_sample_data_populate_fallback_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(db_mod, "_kuzu", None)
    subprocess.run(["python", str(GEN)], check=True, env=ENV)

    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "buckets.yaml").write_text("buckets: []\n", encoding="utf-8")
    (config_dir / "sources.yaml").write_text(
        f"sources:\n  - type: folder\n    label: generated\n    path: {GENERATED}\n",
        encoding="utf-8",
    )

    db_path = data_dir / "archive_index.kuzu"
    assert cli.main(["--data-dir", str(data_dir), "init-db"]) == 0
    assert cli.main(["--data-dir", str(data_dir), "--config-dir", str(config_dir), "ingest", "--source", "generated"]) == 0
    assert "ingested" in capsys.readouterr().out
    assert cli.main(["--data-dir", str(data_dir), "--config-dir", str(config_dir), "ingest", "--source", "generated"]) == 0
    assert "ingested 0 items" in capsys.readouterr().out

    bookmark_file = tmp_path / "bookmarks.html"
    bookmark_file.write_text(
        '<DL><p><DT><H3>Generated</H3><DL><p><DT><A HREF="https://example.com/generated">Generated bookmark</A>',
        encoding="utf-8",
    )
    assert cli.main(["--data-dir", str(data_dir), "ingest-bookmarks", str(bookmark_file)]) == 0
    assert cli.main(["--data-dir", str(data_dir), "embed"]) == 0
    assert cli.main(["--data-dir", str(data_dir), "ocr-videos"]) == 0
    assert cli.main(["--data-dir", str(data_dir), "--config-dir", str(config_dir), "assign-buckets"]) == 0

    conn = db_mod.connect_db(db_path)
    try:
        assert conn.is_fallback
        assert (db_path / "fallback_store.json").exists()
        store = conn.store
        corpus = load_json(GENERATED / "manifests" / "corpus_manifest.json")
        expected_paths = {str((ROOT / item["path"]).resolve()) for item in corpus}
        stored_paths = {row["path_or_url"] for row in store["items"].values()}
        assert expected_paths <= stored_paths
        assert "https://example.com/generated" in stored_paths

        items_by_path = {row["path_or_url"]: row for row in store["items"].values()}
        assert items_by_path[str((GENERATED / "audio" / "fake_audio_voice_note_001.wav").resolve())]["item_type"] == "audio"
        assert items_by_path[str((GENERATED / "video" / "fake_video_local_llm_setup_001.webm").resolve())]["item_type"] == "video"
        assert items_by_path["https://example.com/generated"]["item_type"] == "bookmark"

        chunk_types = {row["chunk_type"] for row in store["chunks"].values()}
        assert {"path_metadata", "audio_metadata", "video_metadata", "bookmark_metadata", "frame_ocr"} <= chunk_types
        assert any("fake_video_local_llm_setup_001.webm" in (row["text"] or "") for row in store["chunks"].values())
        assert any(row["model"] == "nomic-embed-text" for row in store["embeddings"].values())
        assert len(store["item_buckets"]) == len(store["items"])
        assert {row["bucket_name"] for row in store["item_buckets"].values()} == {"review_later"}

        first = next(iter(expected_paths))
    finally:
        conn.close()

    assert cli.main(["--data-dir", str(data_dir), "show-item", first]) == 0
    assert first in capsys.readouterr().out
    assert cli.main(["--data-dir", str(data_dir), "explain-buckets", first]) == 0
    assert "review_later" in capsys.readouterr().out
    assert cli.main(["--data-dir", str(data_dir), "list-bucket", "review_later"]) == 0
    assert first in capsys.readouterr().out
    assert cli.main(["--data-dir", str(data_dir), "bucket-stats"]) == 0
    assert "review_later" in capsys.readouterr().out
    assert cli.main(["--data-dir", str(data_dir), "search", "fake_video_local_llm_setup_001"]) == 0
    assert "fake_video_local_llm_setup_001.webm" in capsys.readouterr().out
    assert cli.main(["--data-dir", str(data_dir)]) == 0
