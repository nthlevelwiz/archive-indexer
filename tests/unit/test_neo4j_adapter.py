from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import create_autospec, patch

import pytest

from archive_indexer.adapters import db as db_mod


class FakeRecord(dict):
    pass


class RecordingTx:
    def __init__(self, driver: "RecordingDriver", mode: str):
        self.driver = driver
        self.mode = mode

    def run(self, query: str, parameters=None, **kwargs):
        if kwargs:
            raise TypeError(f"Unexpected keyword parameters: {kwargs}")
        params = parameters or {}
        cypher = query
        self.driver.calls.append({"mode": self.mode, "cypher": cypher, "params": params})
        for marker, rows in self.driver.rows_by_marker.items():
            if marker in cypher:
                return [FakeRecord(row) for row in rows]
        return []


class RecordingSession:
    def __init__(self, driver: "RecordingDriver", database: str | None):
        self.driver = driver
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute_write(self, func, *args, **kwargs):
        self.driver.session_databases.append(self.database)
        return func(RecordingTx(self.driver, "write"), *args, **kwargs)

    def execute_read(self, func, *args, **kwargs):
        self.driver.session_databases.append(self.database)
        return func(RecordingTx(self.driver, "read"), *args, **kwargs)


class RecordingDriver:
    def __init__(self, rows_by_marker: dict[str, list[dict]] | None = None):
        self.rows_by_marker = rows_by_marker or {}
        self.calls: list[dict] = []
        self.session_databases: list[str | None] = []
        self.closed = False

    def session(self, database=None):
        return RecordingSession(self, database)

    def close(self):
        self.closed = True


def make_adapter(rows_by_marker: dict[str, list[dict]] | None = None):
    adapter = db_mod.Neo4jDatabaseAdapter.__new__(db_mod.Neo4jDatabaseAdapter)
    driver = RecordingDriver(rows_by_marker)
    adapter.driver = driver
    adapter.database = "neo4j"
    return adapter, driver


def assert_last_call(driver: RecordingDriver, mode: str, cypher_contains: str, **params):
    call = driver.calls[-1]
    assert call["mode"] == mode
    assert cypher_contains in call["cypher"]
    for key, value in params.items():
        assert call["params"][key] == value


def test_neo4j_init_schema_writes_constraints_and_fulltext_index():
    adapter, driver = make_adapter()

    adapter.init_schema()

    assert len(driver.calls) == 8
    assert all(call["mode"] == "write" for call in driver.calls)
    assert all(database == "neo4j" for database in driver.session_databases)
    cyphers = [call["cypher"] for call in driver.calls]
    assert "CREATE CONSTRAINT source_id IF NOT EXISTS FOR (n:Source) REQUIRE n.id IS UNIQUE" in cyphers
    assert "CREATE CONSTRAINT item_id IF NOT EXISTS FOR (n:Item) REQUIRE n.id IS UNIQUE" in cyphers
    assert "CREATE FULLTEXT INDEX chunkText IF NOT EXISTS FOR (n:Chunk) ON EACH [n.text]" in cyphers


def test_neo4j_close_and_commit_are_safe():
    adapter, driver = make_adapter()

    assert adapter.commit() is None
    adapter.close()

    assert driver.closed is True


def test_neo4j_source_item_chunk_and_fts_writes():
    adapter, driver = make_adapter()

    adapter.upsert_source("s1", "/archive", "Archive", "{}")
    assert_last_call(driver, "write", "MERGE (s:Source {id: $id})", id="s1", source_type="folder", root_path="/archive", label="Archive", config_json="{}")

    adapter.upsert_bookmark_source("bm1", "/bookmarks.html", "Bookmarks", "{}")
    assert_last_call(driver, "write", "MERGE (s:Source {id: $id})", id="bm1", source_type="bookmark_html", root_path="/bookmarks.html", label="Bookmarks", config_json="{}")

    item_values = ("i1", "s1", "file", "/archive/a.txt", "a.txt", ".txt", "text/plain", 12, "mtime", "hash", "{}", "indexed")
    adapter.upsert_item(item_values)
    assert_last_call(driver, "write", "MERGE (i:Item {id: $id})", id="i1", source_id="s1")
    assert driver.calls[-1]["params"]["props"]["path_or_url"] == "/archive/a.txt"

    chunk_values = ("c1", "i1", "path_metadata", "hello", "{}", "created")
    adapter.upsert_chunk(chunk_values)
    assert_last_call(driver, "write", "MERGE (c:Chunk {id: $id})", id="c1", item_id="i1")
    assert driver.calls[-1]["params"]["props"]["text"] == "hello"

    adapter.insert_fts("c1", "updated text")
    assert_last_call(driver, "write", "MATCH (c:Chunk {id: $chunk_id}) SET c.text=$text", chunk_id="c1", text="updated text")


def test_neo4j_bucket_rule_and_assignment_writes():
    adapter, driver = make_adapter()

    adapter.upsert_bucket_definition("electrical", "Electrical docs", "topic")
    assert_last_call(driver, "write", "MERGE (b:BucketDefinition {name: $name})", name="electrical", description="Electrical docs", bucket_type="topic")

    adapter.insert_bucket_rule("r1", "electrical", "text_regex", "electric", 2.0, "text")
    assert_last_call(driver, "write", "MERGE (r:BucketRule {id: $id})", id="r1", bucket_name="electrical", rule_type="text_regex", pattern="electric", weight=2.0, applies_to="text")

    adapter.upsert_item_bucket("i1", "electrical", 0.9, '[{"pattern":"electric"}]', "rules", "assigned")
    assert_last_call(driver, "write", "MERGE (i)-[rel:IN_BUCKET]->(b)", item_id="i1", bucket_name="electrical", confidence=0.9, evidence_json='[{"pattern":"electric"}]', assigned_by="rules", assigned_at="assigned")


def test_neo4j_embedding_and_ocr_writes():
    adapter, driver = make_adapter()

    adapter.insert_embedding("e1", "c1", "nomic", "[0.1, 0.2]", 2)
    assert_last_call(driver, "write", "MERGE (e:Embedding {id: $id})", id="e1", chunk_id="c1", model="nomic", embedding_json="[0.1, 0.2]", dimensions=2)

    adapter.insert_frame_ocr_chunk("c2", "i1", "ocr text")
    assert_last_call(driver, "write", "MERGE (c:Chunk {id: $id})", item_id="i1", id="c2")
    assert driver.calls[-1]["params"]["props"]["chunk_type"] == "frame_ocr"
    assert driver.calls[-1]["params"]["props"]["text"] == "ocr text"


def test_neo4j_lookup_read_methods_return_rows_and_none_paths():
    adapter, driver = make_adapter(
        {
            "RETURN i.id AS id, i.modified_time": [{"id": "i1", "modified_time": "mtime", "size_bytes": 10}],
            "RETURN c.id AS id": [{"id": "c1"}],
            "RETURN properties(i) AS props": [{"props": {"id": "i1", "path_or_url": "/archive/a.txt"}}],
        }
    )

    assert adapter.get_item_row_by_path("/archive/a.txt") == {"id": "i1", "modified_time": "mtime", "size_bytes": 10}
    assert_last_call(driver, "read", "MATCH (i:Item {path_or_url: $path_or_url})", path_or_url="/archive/a.txt")

    assert adapter.get_chunk_by_item_and_type("i1", "path_metadata") == {"id": "c1"}
    assert_last_call(driver, "read", "MATCH (:Item {id: $item_id})", item_id="i1", chunk_type="path_metadata")

    assert adapter.fetch_item_by_path_or_url("/archive/a.txt") == {"id": "i1", "path_or_url": "/archive/a.txt"}
    assert_last_call(driver, "read", "RETURN properties(i) AS props", path_or_url="/archive/a.txt")

    empty_adapter, _ = make_adapter()
    assert empty_adapter.get_item_row_by_path("missing") is None
    assert empty_adapter.get_chunk_by_item_and_type("i1", "missing") is None
    assert empty_adapter.fetch_item_by_path_or_url("missing") is None


def test_neo4j_collection_read_methods_forward_expected_queries_and_params():
    adapter, driver = make_adapter(
        {
            "MATCH (i:Item) RETURN i.id AS id": [{"id": "i1", "path_or_url": "/a", "filename": "a", "extension": ".txt", "metadata_json": "{}"}],
            "CALL db.index.fulltext.queryNodes('chunkText'": [{"path_or_url": "/a", "text": "hello"}],
            "MATCH (c:Chunk) RETURN c.id AS id": [{"id": "c1", "text": "hello"}],
            "HAS_EMBEDDING]->(e:Embedding {model: $model})": [{"path_or_url": "/a", "text": "hello", "embedding_json": "[1]"}],
            "MATCH (i:Item {item_type: 'video'})": [{"id": "v1", "path_or_url": "/v.mp4"}],
            "RETURN b.name AS bucket_name, rel.confidence": [{"bucket_name": "electrical", "confidence": 0.8, "evidence_json": "[]"}],
            "RETURN i.path_or_url AS path_or_url": [{"path_or_url": "/a"}],
            "RETURN b.name AS bucket_name, count(*) AS c": [{"bucket_name": "electrical", "c": 2}],
        }
    )

    assert adapter.fetch_items_for_bucket_assignment()[0]["id"] == "i1"
    assert_last_call(driver, "read", "MATCH (i:Item) RETURN i.id AS id")

    assert adapter.search_chunks("hello") == [{"path_or_url": "/a", "text": "hello"}]
    assert_last_call(driver, "read", "CALL db.index.fulltext.queryNodes('chunkText'", query="hello")
    assert "bucket" not in driver.calls[-1]["params"]

    assert adapter.search_chunks("hello", bucket="electrical") == [{"path_or_url": "/a", "text": "hello"}]
    assert_last_call(driver, "read", "MATCH (i)-[:IN_BUCKET]->(:BucketDefinition {name: $bucket})", query="hello", bucket="electrical")

    assert adapter.fetch_chunks_for_embedding() == [{"id": "c1", "text": "hello"}]
    assert_last_call(driver, "read", "MATCH (c:Chunk) RETURN c.id AS id")

    assert adapter.fetch_semantic_search_rows("nomic") == [{"path_or_url": "/a", "text": "hello", "embedding_json": "[1]"}]
    assert_last_call(driver, "read", "e:Embedding {model: $model}", model="nomic")

    assert adapter.fetch_video_items() == [{"id": "v1", "path_or_url": "/v.mp4"}]
    assert_last_call(driver, "read", "MATCH (i:Item {item_type: 'video'})")

    assert adapter.fetch_item_bucket_explanations("/a") == [{"bucket_name": "electrical", "confidence": 0.8, "evidence_json": "[]"}]
    assert_last_call(driver, "read", "RETURN b.name AS bucket_name, rel.confidence", path_or_url="/a")

    assert adapter.fetch_bucket_contents("electrical") == [{"path_or_url": "/a"}]
    assert_last_call(driver, "read", "MATCH (i:Item)-[:IN_BUCKET]->(:BucketDefinition {name: $bucket_name})", bucket_name="electrical")

    assert adapter.fetch_bucket_stats() == [{"bucket_name": "electrical", "c": 2}]
    assert_last_call(driver, "read", "RETURN b.name AS bucket_name, count(*) AS c")


def test_neo4j_embedding_exists_true_and_false():
    adapter, driver = make_adapter({"RETURN 1 AS exists": [{"exists": 1}]})
    assert adapter.embedding_exists("c1", "nomic") is True
    assert_last_call(driver, "read", "RETURN 1 AS exists", chunk_id="c1", model="nomic")

    empty_adapter, empty_driver = make_adapter()
    assert empty_adapter.embedding_exists("c1", "nomic") is False
    assert_last_call(empty_driver, "read", "RETURN 1 AS exists", chunk_id="c1", model="nomic")


def _fake_neo4j_modules():
    class Driver:
        def session(self, *, database=None):
            return None

        def close(self):
            return None

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute_read(self, transaction_function, *args, **kwargs):
            return None

        def execute_write(self, transaction_function, *args, **kwargs):
            return None

    class Transaction:
        def run(self, query, parameters=None, **kwargs):
            return None

    class GraphDatabase:
        @staticmethod
        def driver(uri, *, auth=None, **config):
            return None

    neo4j_module = ModuleType("neo4j")
    neo4j_module.GraphDatabase = GraphDatabase
    sync_module = ModuleType("neo4j._sync")
    driver_module = ModuleType("neo4j._sync.driver")
    driver_module.Driver = Driver
    work_module = ModuleType("neo4j._sync.work")
    work_module.Session = Session
    work_module.Transaction = Transaction
    return {
        "neo4j": neo4j_module,
        "neo4j._sync": sync_module,
        "neo4j._sync.driver": driver_module,
        "neo4j._sync.work": work_module,
    }


def test_execute_read_uses_injected_neo4j_package_when_dependency_is_absent():
    with patch.dict(sys.modules, _fake_neo4j_modules()):
        from neo4j._sync.driver import Driver
        from neo4j._sync.work import Session, Transaction

        tx = create_autospec(Transaction, instance=True, spec_set=True)
        session = create_autospec(Session, instance=True, spec_set=True)
        driver = create_autospec(Driver, instance=True, spec_set=True)
        calls: dict[str, object] = {}

        def run_side_effect(query, parameters=None, **kwargs):
            if kwargs:
                raise TypeError(f"Unexpected keyword parameters: {kwargs}")
            calls["cypher"] = query
            calls["params"] = parameters or {}
            return [FakeRecord(path_or_url="/tmp/a.txt", text="hello")]

        def execute_read_side_effect(func, *args, **kwargs):
            return func(tx, *args, **kwargs)

        tx.run.side_effect = run_side_effect
        session.__enter__.return_value = session
        session.__exit__.return_value = False
        session.execute_read.side_effect = execute_read_side_effect
        driver.session.return_value = session

        adapter = db_mod.Neo4jDatabaseAdapter.__new__(db_mod.Neo4jDatabaseAdapter)
        adapter.driver = driver
        adapter.database = "neo4j"

        rows = adapter._execute_read("RETURN $query AS text", query="needle")

        assert rows == [{"path_or_url": "/tmp/a.txt", "text": "hello"}]
        driver.session.assert_called_once_with(database="neo4j")
        session.execute_read.assert_called_once_with(adapter._read_tx, "RETURN $query AS text", {"query": "needle"})
        tx.run.assert_called_once_with("RETURN $query AS text", {"query": "needle"})
        assert calls == {"cypher": "RETURN $query AS text", "params": {"query": "needle"}}


def test_execute_write_uses_injected_neo4j_package_when_dependency_is_absent():
    with patch.dict(sys.modules, _fake_neo4j_modules()):
        from neo4j._sync.driver import Driver
        from neo4j._sync.work import Session, Transaction

        tx = create_autospec(Transaction, instance=True, spec_set=True)
        session = create_autospec(Session, instance=True, spec_set=True)
        driver = create_autospec(Driver, instance=True, spec_set=True)
        calls: dict[str, object] = {}

        def run_side_effect(query, parameters=None, **kwargs):
            if kwargs:
                raise TypeError(f"Unexpected keyword parameters: {kwargs}")
            calls["cypher"] = query
            calls["params"] = parameters or {}
            return []

        def execute_write_side_effect(func, *args, **kwargs):
            return func(tx, *args, **kwargs)

        tx.run.side_effect = run_side_effect
        session.__enter__.return_value = session
        session.__exit__.return_value = False
        session.execute_write.side_effect = execute_write_side_effect
        driver.session.return_value = session

        adapter = db_mod.Neo4jDatabaseAdapter.__new__(db_mod.Neo4jDatabaseAdapter)
        adapter.driver = driver
        adapter.database = "neo4j"

        adapter._execute_write("MATCH (n {id: $id}) SET n.name=$name", id="n1", name="Node")

        driver.session.assert_called_once_with(database="neo4j")
        session.execute_write.assert_called_once_with(
            adapter._write_tx,
            "MATCH (n {id: $id}) SET n.name=$name",
            {"id": "n1", "name": "Node"},
        )
        tx.run.assert_called_once_with("MATCH (n {id: $id}) SET n.name=$name", {"id": "n1", "name": "Node"})
        assert calls == {"cypher": "MATCH (n {id: $id}) SET n.name=$name", "params": {"id": "n1", "name": "Node"}}


def test_constructor_uses_injected_neo4j_package_when_dependency_is_absent(monkeypatch: pytest.MonkeyPatch):
    with patch.dict(sys.modules, _fake_neo4j_modules()):
        import neo4j

        driver = object()
        graph_database = create_autospec(neo4j.GraphDatabase, spec_set=True)
        graph_database.driver.return_value = driver

        monkeypatch.setattr(db_mod, "GraphDatabase", graph_database)

        adapter = db_mod.Neo4jDatabaseAdapter("bolt://example:7687", "neo4j", "secret", "archive")

        graph_database.driver.assert_called_once_with("bolt://example:7687", auth=("neo4j", "secret"))
        assert adapter.driver is driver
        assert adapter.database == "archive"


def test_execute_read_uses_autospecced_neo4j_session_and_transaction():
    pytest.importorskip("neo4j")
    from neo4j._sync.driver import Driver
    from neo4j._sync.work import Session, Transaction

    tx = create_autospec(Transaction, instance=True, spec_set=True)
    session = create_autospec(Session, instance=True, spec_set=True)
    driver = create_autospec(Driver, instance=True, spec_set=True)
    calls: dict[str, object] = {}

    def run_side_effect(query, parameters=None, **kwargs):
        if kwargs:
            raise TypeError(f"Unexpected keyword parameters: {kwargs}")
        calls["cypher"] = query
        calls["params"] = parameters or {}
        return [FakeRecord(path_or_url="/tmp/a.txt", text="hello")]

    def execute_read_side_effect(func, *args, **kwargs):
        return func(tx, *args, **kwargs)

    tx.run.side_effect = run_side_effect
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    session.execute_read.side_effect = execute_read_side_effect
    driver.session.return_value = session

    adapter = db_mod.Neo4jDatabaseAdapter.__new__(db_mod.Neo4jDatabaseAdapter)
    adapter.driver = driver
    adapter.database = "neo4j"

    rows = adapter._execute_read("RETURN $query AS text", query="needle")

    assert rows == [{"path_or_url": "/tmp/a.txt", "text": "hello"}]
    driver.session.assert_called_once_with(database="neo4j")
    session.execute_read.assert_called_once_with(adapter._read_tx, "RETURN $query AS text", {"query": "needle"})
    tx.run.assert_called_once_with("RETURN $query AS text", {"query": "needle"})
    assert calls == {"cypher": "RETURN $query AS text", "params": {"query": "needle"}}


def test_execute_write_uses_autospecced_neo4j_session_and_transaction():
    pytest.importorskip("neo4j")
    from neo4j._sync.driver import Driver
    from neo4j._sync.work import Session, Transaction

    tx = create_autospec(Transaction, instance=True, spec_set=True)
    session = create_autospec(Session, instance=True, spec_set=True)
    driver = create_autospec(Driver, instance=True, spec_set=True)
    calls: dict[str, object] = {}

    def run_side_effect(query, parameters=None, **kwargs):
        if kwargs:
            raise TypeError(f"Unexpected keyword parameters: {kwargs}")
        calls["cypher"] = query
        calls["params"] = parameters or {}
        return []

    def execute_write_side_effect(func, *args, **kwargs):
        return func(tx, *args, **kwargs)

    tx.run.side_effect = run_side_effect
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    session.execute_write.side_effect = execute_write_side_effect
    driver.session.return_value = session

    adapter = db_mod.Neo4jDatabaseAdapter.__new__(db_mod.Neo4jDatabaseAdapter)
    adapter.driver = driver
    adapter.database = "neo4j"

    adapter._execute_write("MATCH (n {id: $id}) SET n.name=$name", id="n1", name="Node")

    driver.session.assert_called_once_with(database="neo4j")
    session.execute_write.assert_called_once_with(
        adapter._write_tx,
        "MATCH (n {id: $id}) SET n.name=$name",
        {"id": "n1", "name": "Node"},
    )
    tx.run.assert_called_once_with("MATCH (n {id: $id}) SET n.name=$name", {"id": "n1", "name": "Node"})
    assert calls == {"cypher": "MATCH (n {id: $id}) SET n.name=$name", "params": {"id": "n1", "name": "Node"}}


def test_neo4j_constructor_uses_autospecced_driver_factory(monkeypatch: pytest.MonkeyPatch):
    neo4j = pytest.importorskip("neo4j")
    driver = object()
    graph_database = create_autospec(neo4j.GraphDatabase, spec_set=True)
    graph_database.driver.return_value = driver

    monkeypatch.setattr(db_mod, "GraphDatabase", graph_database)

    adapter = db_mod.Neo4jDatabaseAdapter("bolt://example:7687", "neo4j", "secret", "archive")

    graph_database.driver.assert_called_once_with("bolt://example:7687", auth=("neo4j", "secret"))
    assert adapter.driver is driver
    assert adapter.database == "archive"


def test_neo4j_constructor_uses_driver_factory(monkeypatch: pytest.MonkeyPatch):
    calls: dict[str, object] = {}

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            calls["uri"] = uri
            calls["auth"] = auth
            return RecordingDriver()

    monkeypatch.setattr(db_mod, "GraphDatabase", FakeGraphDatabase)

    adapter = db_mod.Neo4jDatabaseAdapter("bolt://example:7687", "neo4j", "secret", "archive")

    assert calls == {"uri": "bolt://example:7687", "auth": ("neo4j", "secret")}
    assert adapter.database == "archive"
    assert isinstance(adapter.driver, RecordingDriver)


def test_neo4j_constructor_requires_driver(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(db_mod, "GraphDatabase", None)

    with pytest.raises(RuntimeError, match="neo4j package is required"):
        db_mod.Neo4jDatabaseAdapter("bolt://example:7687", "neo4j", "secret")
