"""Shared pytest fixtures for the zhar test suite."""
from pathlib import Path
import pytest

from zhar.mem.backends.json_backend import JsonBackend
from zhar.mem.index import MemIndex
from zhar.mem.node import make_node
from zhar.mem.query import QueryEngine


@pytest.fixture
def tmp_store(tmp_path) -> JsonBackend:
    """A fresh JsonBackend backed by a temp file."""
    return JsonBackend(tmp_path / "store.json")


@pytest.fixture
def empty_index() -> MemIndex:
    return MemIndex()


@pytest.fixture
def populated_index_and_store(tmp_path):
    """Index + JsonBackend with a small set of nodes across multiple groups."""
    index = MemIndex()
    backend = JsonBackend(tmp_path / "store.json")
    nodes = [
        make_node(group="project_dna",     node_type="core_goal",   summary="Ship v1",         tags=["goal"],         status="active"),
        make_node(group="problem_tracking", node_type="known_issue", summary="Race condition",   tags=["auth", "race"], status="active"),
        make_node(group="decision_trail",   node_type="adr",         summary="Use JWT",          tags=["auth", "jwt"],  status="accepted"),
    ]
    for n in nodes:
        backend.save(n)
        index.add(n)
    return index, backend, nodes


@pytest.fixture
def query_engine(populated_index_and_store) -> QueryEngine:
    index, backend, _ = populated_index_and_store
    return QueryEngine(index=index, backend=backend)
