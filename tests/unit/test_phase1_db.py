print("running tests/unit/test_phase1_db.py")
import os
import subprocess
from pathlib import Path

import pytest

from archive_indexer.adapters import db as db_mod

ROOT = Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def test_init_db_fails_loudly_without_neo4j_config(tmp_path: Path):
    env = {k: v for k, v in ENV.items() if not k.startswith("NEO4J_")}
    result = subprocess.run(
        ["python", "-m", "archive_indexer", "--data-dir", str(tmp_path / "data"), "init-db"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "NEO4J_URI is required" in result.stderr
    assert not (tmp_path / "data" / "archive_graph.json").exists()


def test_connect_db_rejects_file_path_fallback(tmp_path: Path):
    with pytest.raises(RuntimeError, match="Local file-backed databases are no longer supported"):
        db_mod.connect_db(tmp_path / "archive_graph.json")


def test_env_neo4j_connection_details_attempt_neo4j_and_fail_without_fallback(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    env_keys = ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "NEO4J_DATABASE"]
    original_env = {key: os.environ.get(key) for key in env_keys}
    original_config = (
        db_mod._neo4j_uri,
        db_mod._neo4j_user,
        db_mod._neo4j_password,
        db_mod._neo4j_database,
    )
    original_graph_database = db_mod.GraphDatabase
    calls: dict[str, object] = {}

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_write(self, func, *args, **kwargs):
            raise ConnectionRefusedError("neo4j server is unavailable")

    class FakeDriver:
        def session(self, database=None):
            calls["database"] = database
            return FakeSession()

        def close(self):
            calls["closed"] = True

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            calls["uri"] = uri
            calls["auth"] = auth
            return FakeDriver()

    try:
        os.environ["NEO4J_URI"] = "bolt://127.0.0.1:17687"
        os.environ["NEO4J_USER"] = "neo4j"
        os.environ["NEO4J_PASSWORD"] = "test-password"
        os.environ["NEO4J_DATABASE"] = "neo4j"
        db_mod.set_neo4j_config(
            os.environ["NEO4J_URI"],
            os.environ["NEO4J_USER"],
            os.environ["NEO4J_PASSWORD"],
            os.environ["NEO4J_DATABASE"],
        )
        db_mod.set_data_dir(tmp_path / "data")

        db_mod.GraphDatabase = FakeGraphDatabase
        with pytest.raises(ConnectionRefusedError, match="neo4j server is unavailable"):
            db_mod.init_db()

        captured = capsys.readouterr()
        assert "fallback" not in captured.err.lower()
        assert not (tmp_path / "data" / "archive_graph.json").exists()
        assert calls == {
            "uri": "bolt://127.0.0.1:17687",
            "auth": ("neo4j", "test-password"),
            "database": "neo4j",
            "closed": True,
        }
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        (
            db_mod._neo4j_uri,
            db_mod._neo4j_user,
            db_mod._neo4j_password,
            db_mod._neo4j_database,
        ) = original_config
        db_mod.GraphDatabase = original_graph_database


def test_neo4j_execute_read_allows_query_cypher_parameter():
    calls: dict[str, object] = {}

    class FakeRecord(dict):
        pass

    class FakeTx:
        def run(self, query, parameters=None, **kwargs):
            if kwargs:
                raise TypeError(f"Unexpected keyword parameters: {kwargs}")
            calls["cypher"] = query
            calls["params"] = parameters or {}
            return [FakeRecord(path_or_url="/tmp/a.txt", text="hello")]

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_read(self, func, *args, **kwargs):
            return func(FakeTx(), *args, **kwargs)

    class FakeDriver:
        def session(self, database=None):
            calls["database"] = database
            return FakeSession()

        def close(self):
            pass

    adapter = db_mod.Neo4jDatabaseAdapter.__new__(db_mod.Neo4jDatabaseAdapter)
    adapter.driver = FakeDriver()
    adapter.database = "neo4j"

    rows = adapter._execute_read("RETURN $query AS text", query="needle")

    assert rows == [{"path_or_url": "/tmp/a.txt", "text": "hello"}]
    assert calls == {
        "database": "neo4j",
        "cypher": "RETURN $query AS text",
        "params": {"query": "needle"},
    }
