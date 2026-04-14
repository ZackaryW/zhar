"""TDD: zhar.mem.store — MemStore coordinator."""
from pathlib import Path
import pytest

from zhar.mem.node import make_node, patch_node
from zhar.mem.query import Query
from zhar.mem.store import MemStore


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path) -> MemStore:
    """A fresh MemStore rooted at a temp directory."""
    return MemStore(tmp_path)


@pytest.fixture
def goal_node():
    return make_node(
        group="project_dna",
        node_type="core_goal",
        summary="Ship zhar v1",
        tags=["goal"],
        metadata={"agent": "claude"},
    )


@pytest.fixture
def issue_node():
    return make_node(
        group="problem_tracking",
        node_type="known_issue",
        summary="Race condition in token refresh",
        tags=["auth"],
        metadata={"severity": "high", "agent": "claude"},
    )


# ── initialisation ────────────────────────────────────────────────────────────

class TestInit:
    def test_store_dir_created_on_init(self, tmp_path):
        s = MemStore(tmp_path)
        assert s.store_dir.exists()

    def test_store_dir_is_subdir_of_root(self, tmp_path):
        s = MemStore(tmp_path)
        assert s.store_dir.parent == tmp_path

    def test_groups_loaded(self, store):
        assert "project_dna" in store.groups
        assert "problem_tracking" in store.groups
        assert "decision_trail" in store.groups
        assert "code_history" in store.groups

    def test_index_starts_empty(self, store):
        assert store.index.count() == 0


# ── save / get ────────────────────────────────────────────────────────────────

class TestSaveGet:
    def test_save_returns_node(self, store, goal_node):
        result = store.save(goal_node)
        assert result.id == goal_node.id

    def test_get_returns_saved_node(self, store, goal_node):
        store.save(goal_node)
        result = store.get(goal_node.id)
        assert result is not None
        assert result.id == goal_node.id

    def test_get_unknown_id_returns_none(self, store):
        assert store.get("0000") is None

    def test_save_indexes_node(self, store, goal_node):
        store.save(goal_node)
        ref = store.index.get(goal_node.id)
        assert ref is not None
        assert ref.group == "project_dna"

    def test_save_to_multiple_groups(self, store, goal_node, issue_node):
        store.save(goal_node)
        store.save(issue_node)
        assert store.index.count() == 2
        assert store.get(goal_node.id) is not None
        assert store.get(issue_node.id) is not None

    def test_overwrite_updates_index(self, store, goal_node):
        store.save(goal_node)
        updated = patch_node(goal_node, summary="Updated goal")
        store.save(updated)
        assert store.get(goal_node.id).summary == "Updated goal"

    def test_save_strips_redundant_file_change_path_when_source_present(self, store):
        node = make_node(
            group="code_history",
            node_type="file_change",
            summary="stack template parser",
            source="src/zhar/stack/template.py::26::%ZHAR:ffff%",
            metadata={
                "path": "src/zhar/stack/template.py",
                "significance": "feature",
            },
        )

        saved = store.save(node)

        assert "path" not in saved.metadata
        assert "path" not in store.get(node.id).metadata


# ── delete ────────────────────────────────────────────────────────────────────

class TestDelete:
    def test_delete_returns_true_when_existed(self, store, goal_node):
        store.save(goal_node)
        assert store.delete(goal_node.id) is True

    def test_delete_returns_false_when_missing(self, store):
        assert store.delete("0000") is False

    def test_delete_removes_from_index(self, store, goal_node):
        store.save(goal_node)
        store.delete(goal_node.id)
        assert store.index.get(goal_node.id) is None

    def test_delete_removes_from_backend(self, store, goal_node):
        store.save(goal_node)
        store.delete(goal_node.id)
        assert store.get(goal_node.id) is None


# ── singleton enforcement ─────────────────────────────────────────────────────

class TestSingletonEnforcement:
    def test_second_core_goal_raises(self, store):
        n1 = make_node(group="project_dna", node_type="core_goal", summary="First goal")
        n2 = make_node(group="project_dna", node_type="core_goal", summary="Second goal")
        store.save(n1)
        with pytest.raises(ValueError, match="singleton"):
            store.save(n2)

    def test_updating_existing_singleton_is_allowed(self, store):
        n = make_node(group="project_dna", node_type="core_goal", summary="Original")
        store.save(n)
        updated = patch_node(n, summary="Revised")
        # Same ID → update, not a second instance
        store.save(updated)
        assert store.get(n.id).summary == "Revised"


# ── memory_backed enforcement ─────────────────────────────────────────────────

class TestMemoryBackedEnforcement:
    def test_content_on_backed_type_accepted(self, store):
        n = make_node(group="problem_tracking", node_type="known_issue",
                      summary="Bug", content="## Details\n\nbody")
        store.save(n)
        assert store.get(n.id).content == "## Details\n\nbody"

    def test_content_on_non_backed_type_raises(self, store):
        n = make_node(group="project_dna", node_type="core_goal",
                      summary="Goal", content="some body")
        with pytest.raises(ValueError, match="memory_backed"):
            store.save(n)

    def test_none_content_on_non_backed_type_accepted(self, store):
        n = make_node(group="project_dna", node_type="core_goal",
                      summary="Goal", content=None)
        store.save(n)
        assert store.get(n.id).content is None


class TestStatusValidation:
    def test_invalid_status_raises(self, store):
        n = make_node(
            group="project_dna",
            node_type="core_requirement",
            summary="Bad status",
            status="resolved",
        )

        with pytest.raises(ValueError, match="Invalid status"):
            store.save(n)


# ── query ─────────────────────────────────────────────────────────────────────

class TestQuery:
    def test_query_all_returns_saved_nodes(self, store, goal_node, issue_node):
        store.save(goal_node)
        store.save(issue_node)
        results = store.query(Query())
        ids = {n.id for n in results}
        assert goal_node.id in ids
        assert issue_node.id in ids

    def test_query_by_group_filters(self, store, goal_node, issue_node):
        store.save(goal_node)
        store.save(issue_node)
        results = store.query(Query(groups=["project_dna"]))
        assert all(n.group == "project_dna" for n in results)

    def test_query_by_tag_filters(self, store, goal_node, issue_node):
        store.save(goal_node)
        store.save(issue_node)
        results = store.query(Query(tags=["auth"]))
        assert all("auth" in n.tags for n in results)

    def test_query_summary_contains(self, store, goal_node, issue_node):
        store.save(goal_node)
        store.save(issue_node)
        results = store.query(Query(summary_contains="race"))
        assert len(results) == 1
        assert results[0].id == issue_node.id


# ── reload from disk ──────────────────────────────────────────────────────────

class TestReload:
    def test_new_store_instance_sees_saved_nodes(self, tmp_path, goal_node):
        s1 = MemStore(tmp_path)
        s1.save(goal_node)

        s2 = MemStore(tmp_path)
        assert s2.get(goal_node.id) is not None

    def test_new_store_index_rebuilt_from_disk(self, tmp_path, goal_node):
        s1 = MemStore(tmp_path)
        s1.save(goal_node)

        s2 = MemStore(tmp_path)
        assert s2.index.get(goal_node.id) is not None


# ── stats ─────────────────────────────────────────────────────────────────────

class TestStats:
    def test_stats_returns_counts_per_group(self, store, goal_node, issue_node):
        store.save(goal_node)
        store.save(issue_node)
        stats = store.stats()
        assert stats["project_dna"]["total"] >= 1
        assert stats["problem_tracking"]["total"] >= 1

    def test_stats_empty_store_all_zeros(self, store):
        stats = store.stats()
        for group_stats in stats.values():
            assert group_stats["total"] == 0
