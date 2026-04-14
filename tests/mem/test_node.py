"""TDD: zhar.mem.node — base Node dataclass."""
from datetime import timezone
import pytest
from zhar.mem.node import Node, NodeRef, make_node, IMMUTABLE_FIELDS
from zhar.utils.times import utcnow


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def minimal_node():
    return make_node(
        group="project_dna",
        node_type="core_goal",
        summary="Build a great product",
    )


@pytest.fixture
def full_node():
    return make_node(
        group="problem_tracking",
        node_type="known_issue",
        summary="Token refresh race condition",
        tags=["auth", "race"],
        status="active",
        source="src/auth.py::%ZHAR:c4d7%",
        metadata={"severity": "high", "agent": "claude"},
        custom={"jira": "AUTH-123"},
    )


# ── make_node ─────────────────────────────────────────────────────────────────

class TestMakeNode:
    def test_returns_node_instance(self, minimal_node):
        assert isinstance(minimal_node, Node)

    def test_id_is_supported_hex_length(self, minimal_node):
        assert len(minimal_node.id) in {4, 5}
        assert all(c in "0123456789abcdef" for c in minimal_node.id)

    def test_group_and_type_set(self, full_node):
        assert full_node.group == "problem_tracking"
        assert full_node.node_type == "known_issue"

    def test_summary_set(self, minimal_node):
        assert minimal_node.summary == "Build a great product"

    def test_default_status_is_active(self, minimal_node):
        assert minimal_node.status == "active"

    def test_custom_status(self):
        n = make_node(group="g", node_type="t", summary="s", status="archived")
        assert n.status == "archived"

    def test_default_tags_empty(self, minimal_node):
        assert minimal_node.tags == []

    def test_tags_set(self, full_node):
        assert "auth" in full_node.tags

    def test_created_at_is_utc_aware(self, minimal_node):
        assert minimal_node.created_at.tzinfo is not None
        assert minimal_node.created_at.utcoffset().total_seconds() == 0

    def test_updated_at_equals_created_at_on_creation(self, minimal_node):
        assert minimal_node.updated_at == minimal_node.created_at

    def test_expires_at_defaults_to_none(self, minimal_node):
        assert minimal_node.expires_at is None

    def test_source_defaults_to_none(self, minimal_node):
        assert minimal_node.source is None

    def test_metadata_defaults_empty(self, minimal_node):
        assert minimal_node.metadata == {}

    def test_custom_defaults_empty(self, minimal_node):
        assert minimal_node.custom == {}

    def test_content_defaults_to_none(self, minimal_node):
        assert minimal_node.content is None

    def test_content_can_be_set(self):
        n = make_node(group="g", node_type="t", summary="s", content="## Details\n\nSome body.")
        assert n.content == "## Details\n\nSome body."

    def test_metadata_and_custom_are_independent_copies(self):
        meta = {"k": "v"}
        custom = {"x": 1}
        n = make_node(group="g", node_type="t", summary="s",
                      metadata=meta, custom=custom)
        meta["k"] = "changed"
        custom["x"] = 99
        assert n.metadata["k"] == "v"
        assert n.custom["x"] == 1


# ── Node immutability ─────────────────────────────────────────────────────────

class TestNodeImmutability:
    def test_id_cannot_be_reassigned(self, minimal_node):
        with pytest.raises((AttributeError, TypeError)):
            minimal_node.id = "0000"  # type: ignore[misc]

    def test_group_cannot_be_reassigned(self, minimal_node):
        with pytest.raises((AttributeError, TypeError)):
            minimal_node.group = "other"  # type: ignore[misc]

    def test_node_type_cannot_be_reassigned(self, minimal_node):
        with pytest.raises((AttributeError, TypeError)):
            minimal_node.node_type = "other"  # type: ignore[misc]

    def test_created_at_cannot_be_reassigned(self, minimal_node):
        with pytest.raises((AttributeError, TypeError)):
            minimal_node.created_at = utcnow()  # type: ignore[misc]

    def test_immutable_fields_list_covers_key_fields(self):
        for field in ("id", "group", "node_type", "created_at"):
            assert field in IMMUTABLE_FIELDS


# ── NodeRef ───────────────────────────────────────────────────────────────────

class TestNodeRef:
    def test_ref_from_node(self, full_node):
        ref = NodeRef.from_node(full_node)
        assert ref.id == full_node.id
        assert ref.group == full_node.group
        assert ref.node_type == full_node.node_type

    def test_ref_is_lightweight(self, full_node):
        ref = NodeRef.from_node(full_node)
        assert not hasattr(ref, "metadata")
        assert not hasattr(ref, "custom")

    def test_ref_equality(self, full_node):
        ref1 = NodeRef.from_node(full_node)
        ref2 = NodeRef.from_node(full_node)
        assert ref1 == ref2


# ── patch helper ─────────────────────────────────────────────────────────────

class TestNodePatch:
    """Patching a node returns a new Node with updated_at refreshed."""

    def test_patch_returns_new_instance(self, minimal_node):
        from zhar.mem.node import patch_node
        patched = patch_node(minimal_node, status="archived")
        assert patched is not minimal_node

    def test_patch_updates_mutable_field(self, minimal_node):
        from zhar.mem.node import patch_node
        patched = patch_node(minimal_node, status="archived")
        assert patched.status == "archived"

    def test_patch_refreshes_updated_at(self, minimal_node):
        from zhar.mem.node import patch_node
        import time; time.sleep(0.01)
        patched = patch_node(minimal_node, summary="changed")
        assert patched.updated_at >= minimal_node.updated_at

    def test_patch_preserves_id(self, minimal_node):
        from zhar.mem.node import patch_node
        patched = patch_node(minimal_node, summary="changed")
        assert patched.id == minimal_node.id

    def test_patch_cannot_change_immutable_fields(self, minimal_node):
        from zhar.mem.node import patch_node
        with pytest.raises((ValueError, TypeError)):
            patch_node(minimal_node, id="0000")

    def test_patch_merges_metadata(self, full_node):
        from zhar.mem.node import patch_node
        patched = patch_node(full_node, metadata={"severity": "critical"})
        assert patched.metadata["severity"] == "critical"
        assert patched.metadata["agent"] == "claude"  # preserved

    def test_patch_merges_custom(self, full_node):
        from zhar.mem.node import patch_node
        patched = patch_node(full_node, custom={"sprint": 42})
        assert patched.custom["sprint"] == 42
        assert patched.custom["jira"] == "AUTH-123"  # preserved

    def test_patch_can_null_custom_key(self, full_node):
        from zhar.mem.node import patch_node
        patched = patch_node(full_node, custom={"jira": None})
        assert "jira" not in patched.custom

    def test_patch_can_set_content(self, minimal_node):
        from zhar.mem.node import patch_node
        patched = patch_node(minimal_node, content="# Body")
        assert patched.content == "# Body"

    def test_patch_can_clear_content(self):
        from zhar.mem.node import patch_node
        n = make_node(group="g", node_type="t", summary="s", content="existing")
        patched = patch_node(n, content=None)
        assert patched.content is None
