from __future__ import annotations

import importlib
import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_BLARIFY_EXTENSIONS_TO_SKIP = (
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".html",
    ".css",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pyc",
)

DEFAULT_BLARIFY_NAMES_TO_SKIP = (
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "data",
    "dist",
    "htmlcov",
    "node_modules",
    "sample_data",
    "src/archive_indexer.egg-info",
)


class BlarifyNotInstalledError(RuntimeError):
    pass


@dataclass(frozen=True)
class BlarifyNeo4jConfig:
    uri: str
    user: str
    password: str
    database: str | None
    repo_id: str
    entity_id: str


@dataclass(frozen=True)
class BlarifyBuildResult:
    node_count: int
    relationship_count: int


def _require_blarify() -> None:
    if importlib.util.find_spec("blarify") is None:
        raise BlarifyNotInstalledError(
            "Blarify is not installed. Install it with `pip install -e .[graph]` "
            "or `pip install blarify` before running code visualization."
        )


def _split_csv(values: Sequence[str] | None, defaults: Sequence[str]) -> list[str]:
    if not values:
        return list(defaults)
    split_values: list[str] = []
    for value in values:
        split_values.extend(part.strip() for part in value.split(",") if part.strip())
    return split_values


def blarify_neo4j_config_from_env(
    *,
    uri: str | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str | None = None,
    repo_id: str | None = None,
    entity_id: str | None = None,
) -> BlarifyNeo4jConfig:
    resolved_uri = uri or os.getenv("NEO4J_URI") or "bolt://localhost:7687"
    resolved_user = user or os.getenv("NEO4J_USER") or "neo4j"
    resolved_password = password or os.getenv("NEO4J_PASSWORD") or "password"
    resolved_database = database or os.getenv("NEO4J_DATABASE") or None
    resolved_repo_id = repo_id or os.getenv("BLARIFY_REPO_ID") or "archive-indexer"
    resolved_entity_id = entity_id or os.getenv("BLARIFY_ENTITY_ID") or "local"
    return BlarifyNeo4jConfig(
        uri=resolved_uri,
        user=resolved_user,
        password=resolved_password,
        database=resolved_database,
        repo_id=resolved_repo_id,
        entity_id=resolved_entity_id,
    )


def build_blarify_graph_in_neo4j(
    *,
    root_path: str | Path,
    config: BlarifyNeo4jConfig,
    extensions_to_skip: Sequence[str] | None = None,
    names_to_skip: Sequence[str] | None = None,
    generate_embeddings: bool = False,
    create_workflows: bool = False,
    create_documentation: bool = False,
) -> BlarifyBuildResult:
    _require_blarify()
    graph_builder_module = importlib.import_module("blarify.prebuilt.graph_builder")
    neo4j_manager_module = importlib.import_module(
        "blarify.repositories.graph_db_manager.neo4j_manager"
    )

    graph_builder_class = graph_builder_module.GraphBuilder
    neo4j_manager_class = neo4j_manager_module.Neo4jManager

    manager_kwargs = {
        "uri": config.uri,
        "user": config.user,
        "password": config.password,
        "repo_id": config.repo_id,
        "entity_id": config.entity_id,
    }
    db_manager = neo4j_manager_class(**manager_kwargs)
    try:
        builder = graph_builder_class(
            root_path=str(Path(root_path).resolve()),
            extensions_to_skip=_split_csv(
                extensions_to_skip, DEFAULT_BLARIFY_EXTENSIONS_TO_SKIP
            ),
            names_to_skip=_split_csv(names_to_skip, DEFAULT_BLARIFY_NAMES_TO_SKIP),
            db_manager=db_manager,
            generate_embeddings=generate_embeddings,
        )
        graph = builder.build(
            save_to_db=True,
            create_workflows=create_workflows,
            create_documentation=create_documentation,
        )
        node_count = len(graph.get_nodes_as_objects())
        relationship_count = len(graph.get_relationships_as_objects())
        return BlarifyBuildResult(
            node_count=node_count, relationship_count=relationship_count
        )
    finally:
        db_manager.close()
