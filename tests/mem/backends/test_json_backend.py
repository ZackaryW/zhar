"""TDD: zhar.mem.backends.json_backend — JSON file persistence."""
import json
from pathlib import Path
import pytest
import orjson
from zhar.mem.node import make_node, patch_node
from zhar.mem.backends.json_backend import JsonBackend, _FILE_CACHE
from zhar.mem.backends.base import Backend
from zhar.utils.cache import MtimeFileCache


@pytest.fixture
def store_path(tmp_path) -> Path:
    return tmp_path / "project_dna.json"


@pytest.fixture
def backend(store_path) -> JsonBackend:
    return JsonBackend(store_path)


@pytest.fixture
def node():
    return make_node(
        group="project_dna",
        node_type="core_goal",
        summary="Ship v1",
        tags=["goal"],
        metadata={"agent": "claude"},
        custom={"sprint": 1},
    )


# ── interface compliance ──────────────────────────────────────────────────────

class TestBackendProtocol:
    def test_implements_backend_protocol(self, backend):
        assert isinstance(backend, Backend)


# ── save + get ────────────────────────────────────────────────────────────────

class TestSaveGet:
    def test_get_returns_none_for_unknown_id(self, backend):
        assert backend.get("0000") is None

    def test_save_then_get_returns_node(self, backend, node):
        backend.save(node)
        result = backend.get(node.id)
        assert result is not None
        assert result.id == node.id

    def test_round_trip_preserves_summary(self, backend, node):
        backend.save(node)
        assert backend.get(node.id).summary == node.summary

    def test_round_trip_preserves_tags(self, backend, node):
        backend.save(node)
        result = backend.get(node.id)
        assert list(result.tags) == list(node.tags)

    def test_round_trip_preserves_metadata(self, backend, node):
        backend.save(node)
        assert backend.get(node.id).metadata == node.metadata

    def test_round_trip_preserves_custom(self, backend, node):
        backend.save(node)
        assert backend.get(node.id).custom == node.custom

    def test_save_overwrites_existing(self, backend, node):
        backend.save(node)
        updated = patch_node(node, summary="Updated summary")
        backend.save(updated)
        result = backend.get(node.id)
        assert result.summary == "Updated summary"


# ── exists ────────────────────────────────────────────────────────────────────

class TestExists:
    def test_false_before_save(self, backend, node):
        assert backend.exists(node.id) is False

    def test_true_after_save(self, backend, node):
        backend.save(node)
        assert backend.exists(node.id) is True

    def test_false_after_delete(self, backend, node):
        backend.save(node)
        backend.delete(node.id)
        assert backend.exists(node.id) is False


# ── delete ────────────────────────────────────────────────────────────────────

class TestDelete:
    def test_returns_true_when_existed(self, backend, node):
        backend.save(node)
        assert backend.delete(node.id) is True

    def test_returns_false_when_not_found(self, backend):
        assert backend.delete("0000") is False

    def test_get_returns_none_after_delete(self, backend, node):
        backend.save(node)
        backend.delete(node.id)
        assert backend.get(node.id) is None


# ── list_all ──────────────────────────────────────────────────────────────────

class TestListAll:
    def test_empty_when_no_nodes(self, backend):
        assert backend.list_all() == []

    def test_returns_saved_nodes(self, backend, node):
        backend.save(node)
        nodes = backend.list_all()
        assert len(nodes) == 1
        assert nodes[0].id == node.id

    def test_returns_all_saved_nodes(self, backend):
        n1 = make_node(group="g", node_type="t", summary="one")
        n2 = make_node(group="g", node_type="t", summary="two")
        n3 = make_node(group="g", node_type="t", summary="three")
        for n in (n1, n2, n3):
            backend.save(n)
        ids = {n.id for n in backend.list_all()}
        assert {n1.id, n2.id, n3.id} == ids


# ── persistence across instances ─────────────────────────────────────────────

class TestPersistence:
    def test_data_survives_new_instance(self, store_path, node):
        b1 = JsonBackend(store_path)
        b1.save(node)
        b2 = JsonBackend(store_path)
        assert b2.get(node.id) is not None

    def test_file_is_valid_json(self, backend, node):
        backend.save(node)
        raw = json.loads(backend._path.read_text())
        assert isinstance(raw, dict)

    def test_file_created_on_first_save(self, store_path, node):
        assert not store_path.exists()
        JsonBackend(store_path).save(node)
        assert store_path.exists()

    def test_parent_dir_created_if_missing(self, tmp_path, node):
        nested = tmp_path / "deep" / "nested" / "store.json"
        JsonBackend(nested).save(node)
        assert nested.exists()


# ── content round-trip ───────────────────────────────────────────────────────

class TestContentField:
    def test_content_none_round_trips(self, backend, node):
        backend.save(node)
        assert backend.get(node.id).content is None

    def test_content_body_round_trips(self, backend):
        n = make_node(group="g", node_type="t", summary="s",
                      content="## Details\n\nFull body.")
        backend.save(n)
        assert backend.get(n.id).content == "## Details\n\nFull body."


# ── orjson always used ────────────────────────────────────────────────────────

class TestOrjsonAlways:
    def test_file_written_as_valid_orjson(self, backend, node):
        """Output must be valid orjson (and standard JSON)."""
        backend.save(node)
        raw = backend._path.read_bytes()
        parsed = orjson.loads(raw)
        assert isinstance(parsed, dict)

    def test_custom_cache_accepted(self, store_path, node):
        """JsonBackend should accept a custom MtimeFileCache instance."""
        custom_cache = MtimeFileCache()
        b = JsonBackend(store_path, cache=custom_cache)
        b.save(node)
        assert b.get(node.id) is not None

    def test_cache_invalidated_after_write(self, backend, node):
        """After save, a second backend on the same file must see the new data."""
        backend.save(node)
        # New backend sharing the same module-level cache
        b2 = JsonBackend(backend._path)
        assert b2.get(node.id) is not None
