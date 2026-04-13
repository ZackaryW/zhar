"""TDD: zhar.mem.index — thin cross-group index."""
import pytest
from zhar.mem.node import make_node, NodeRef
from zhar.mem.index import MemIndex


@pytest.fixture
def index():
    return MemIndex()


@pytest.fixture
def dna_node():
    return make_node(group="project_dna", node_type="core_goal", summary="Ship v1",
                     tags=["goal"], status="active")


@pytest.fixture
def issue_node():
    return make_node(group="problem_tracking", node_type="known_issue",
                     summary="Race condition", tags=["auth", "race"], status="active")


class TestIndexAdd:
    def test_add_node_increases_count(self, index, dna_node):
        assert index.count() == 0
        index.add(dna_node)
        assert index.count() == 1

    def test_add_same_id_twice_overwrites(self, index, dna_node):
        index.add(dna_node)
        index.add(dna_node)
        assert index.count() == 1

    def test_add_returns_noderef(self, index, dna_node):
        ref = index.add(dna_node)
        assert isinstance(ref, NodeRef)
        assert ref.id == dna_node.id


class TestIndexGet:
    def test_get_returns_none_for_unknown(self, index):
        assert index.get("0000") is None

    def test_get_returns_ref_after_add(self, index, dna_node):
        index.add(dna_node)
        ref = index.get(dna_node.id)
        assert ref is not None
        assert ref.id == dna_node.id

    def test_get_ref_has_correct_group(self, index, dna_node):
        index.add(dna_node)
        assert index.get(dna_node.id).group == "project_dna"


class TestIndexRemove:
    def test_remove_existing_returns_true(self, index, dna_node):
        index.add(dna_node)
        assert index.remove(dna_node.id) is True

    def test_remove_missing_returns_false(self, index):
        assert index.remove("0000") is False

    def test_remove_decreases_count(self, index, dna_node):
        index.add(dna_node)
        index.remove(dna_node.id)
        assert index.count() == 0


class TestIndexFilter:
    def test_by_group(self, index, dna_node, issue_node):
        index.add(dna_node)
        index.add(issue_node)
        results = index.by_group("project_dna")
        assert len(results) == 1
        assert results[0].group == "project_dna"

    def test_by_node_type(self, index, dna_node, issue_node):
        index.add(dna_node)
        index.add(issue_node)
        results = index.by_type("known_issue")
        assert len(results) == 1
        assert results[0].node_type == "known_issue"

    def test_by_status(self, index, dna_node, issue_node):
        index.add(dna_node)
        index.add(issue_node)
        results = index.by_status("active")
        assert len(results) == 2

    def test_by_tag_returns_matching(self, index, dna_node, issue_node):
        index.add(dna_node)
        index.add(issue_node)
        results = index.by_tag("auth")
        assert len(results) == 1
        assert results[0].id == issue_node.id

    def test_by_tag_no_match_returns_empty(self, index, dna_node):
        index.add(dna_node)
        results = index.by_tag("nonexistent")
        assert results == []

    def test_all_returns_all_refs(self, index, dna_node, issue_node):
        index.add(dna_node)
        index.add(issue_node)
        all_refs = index.all()
        assert len(all_refs) == 2


class TestIndexSingleton:
    def test_singleton_of_type_returns_none_when_empty(self, index):
        assert index.singleton("project_dna", "core_goal") is None

    def test_singleton_returns_ref_after_add(self, index, dna_node):
        index.add(dna_node)
        ref = index.singleton("project_dna", "core_goal")
        assert ref is not None
        assert ref.id == dna_node.id
