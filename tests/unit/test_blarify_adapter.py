import sys
import types

import pytest

from archive_indexer.adapters import blarify


class FakeGraph:
    def get_nodes_as_objects(self):
        return [{"type": "File"}, {"type": "Function"}]

    def get_relationships_as_objects(self):
        return [{"type": "CONTAINS"}]


class FakeGraphBuilder:
    seen_kwargs = None
    seen_build_kwargs = None

    def __init__(self, **kwargs):
        FakeGraphBuilder.seen_kwargs = kwargs

    def build(self, **kwargs):
        FakeGraphBuilder.seen_build_kwargs = kwargs
        return FakeGraph()


class FakeNeo4jManager:
    seen_kwargs = None
    closed = False

    def __init__(self, **kwargs):
        FakeNeo4jManager.seen_kwargs = kwargs

    def close(self):
        FakeNeo4jManager.closed = True


def test_config_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j.example:7687")
    monkeypatch.setenv("NEO4J_USER", "alice")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("NEO4J_DATABASE", "code")
    monkeypatch.setenv("BLARIFY_REPO_ID", "repo")
    monkeypatch.setenv("BLARIFY_ENTITY_ID", "org")

    config = blarify.blarify_neo4j_config_from_env()

    assert config.uri == "bolt://neo4j.example:7687"
    assert config.user == "alice"
    assert config.password == "secret"
    assert config.database == "code"
    assert config.repo_id == "repo"
    assert config.entity_id == "org"


def test_build_graph_uses_blarify_modules(monkeypatch: pytest.MonkeyPatch, tmp_path):
    root_package = types.ModuleType("blarify")
    root_package.__spec__ = types.SimpleNamespace()
    graph_builder_module = types.ModuleType("blarify.prebuilt.graph_builder")
    graph_builder_module.GraphBuilder = FakeGraphBuilder
    neo4j_module = types.ModuleType("blarify.repositories.graph_db_manager.neo4j_manager")
    neo4j_module.Neo4jManager = FakeNeo4jManager
    monkeypatch.setitem(sys.modules, "blarify", root_package)
    monkeypatch.setitem(sys.modules, "blarify.prebuilt.graph_builder", graph_builder_module)
    monkeypatch.setitem(
        sys.modules,
        "blarify.repositories.graph_db_manager.neo4j_manager",
        neo4j_module,
    )
    monkeypatch.setattr(
        blarify.importlib.util,
        "find_spec",
        lambda name: object() if name == "blarify" else None,
    )

    config = blarify.BlarifyNeo4jConfig(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password",
        database="neo4j",
        repo_id="archive-indexer",
        entity_id="local",
    )
    result = blarify.build_blarify_graph_in_neo4j(
        root_path=tmp_path,
        config=config,
        extensions_to_skip=[".json,.md", ".txt"],
        names_to_skip=["__pycache__,node_modules"],
        generate_embeddings=True,
        create_workflows=True,
        create_documentation=True,
    )

    assert result.node_count == 2
    assert result.relationship_count == 1
    assert FakeNeo4jManager.seen_kwargs == {
        "uri": "bolt://localhost:7687",
        "user": "neo4j",
        "password": "password",
        "repo_id": "archive-indexer",
        "entity_id": "local",
    }
    assert FakeGraphBuilder.seen_kwargs["root_path"] == str(tmp_path.resolve())
    assert FakeGraphBuilder.seen_kwargs["extensions_to_skip"] == [
        ".json",
        ".md",
        ".txt",
    ]
    assert FakeGraphBuilder.seen_kwargs["names_to_skip"] == ["__pycache__", "node_modules"]
    assert FakeGraphBuilder.seen_kwargs["generate_embeddings"] is True
    assert FakeGraphBuilder.seen_build_kwargs == {
        "save_to_db": True,
        "create_workflows": True,
        "create_documentation": True,
    }
    assert FakeNeo4jManager.closed is True
