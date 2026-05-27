import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}

def test_cli_help_lists_init_db_command():
    result = subprocess.run(
        ["python", "-m", "archive_indexer", "--help"],
        check=True,
        capture_output=True,
        text=True,
        env=ENV,
    )
    assert "init-db" in result.stdout
    assert "--data-dir" in result.stdout
