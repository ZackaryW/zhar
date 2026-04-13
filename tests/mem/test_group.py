"""TDD: zhar.mem.group — GroupDef, NodeTypeDef, metadata semantic."""
from dataclasses import dataclass
from typing import Literal
import pytest
from zhar.mem.group import GroupDef, NodeTypeDef, validate_node_metadata


# ── fixtures ──────────────────────────────────────────────────────────────────

@dataclass
class GoalMeta:
    agent: str = ""
    priority: Literal["low", "med", "high"] = "med"


@dataclass
class IssueMeta:
    severity: Literal["low", "med", "high", "critical"] = "med"
    agent: str = ""


@pytest.fixture
def goal_type():
    return NodeTypeDef(
        name="core_goal",
        meta_cls=GoalMeta,
        valid_statuses=["active", "archived"],
        default_status="active",
        singleton=True,
    )


@pytest.fixture
def issue_type():
    return NodeTypeDef(
        name="known_issue",
        meta_cls=IssueMeta,
        valid_statuses=["active", "resolved", "archived"],
        default_status="active",
    )


@pytest.fixture
def sample_group(goal_type, issue_type):
    return GroupDef(
        name="test_group",
        node_types=[goal_type, issue_type],
    )


# ── NodeTypeDef ───────────────────────────────────────────────────────────────

class TestNodeTypeDef:
    def test_name_stored(self, goal_type):
        assert goal_type.name == "core_goal"

    def test_meta_cls_stored(self, goal_type):
        assert goal_type.meta_cls is GoalMeta

    def test_valid_statuses_stored(self, goal_type):
        assert "active" in goal_type.valid_statuses
        assert "archived" in goal_type.valid_statuses

    def test_default_status_must_be_in_valid_statuses(self):
        with pytest.raises(ValueError):
            NodeTypeDef(
                name="bad",
                meta_cls=GoalMeta,
                valid_statuses=["active"],
                default_status="unknown",
            )

    def test_singleton_default_false(self, issue_type):
        assert issue_type.singleton is False

    def test_singleton_true(self, goal_type):
        assert goal_type.singleton is True

    def test_memory_backed_defaults_false(self, issue_type):
        assert issue_type.memory_backed is False

    def test_memory_backed_can_be_set_true(self):
        nt = NodeTypeDef(
            name="doc",
            meta_cls=GoalMeta,
            valid_statuses=["active"],
            memory_backed=True,
        )
        assert nt.memory_backed is True


# ── GroupDef ──────────────────────────────────────────────────────────────────

class TestGroupDef:
    def test_name_stored(self, sample_group):
        assert sample_group.name == "test_group"

    def test_node_type_lookup_by_name(self, sample_group):
        nt = sample_group.get_type("core_goal")
        assert nt.name == "core_goal"

    def test_unknown_type_raises(self, sample_group):
        with pytest.raises(KeyError):
            sample_group.get_type("nonexistent")

    def test_type_names_property(self, sample_group):
        names = sample_group.type_names
        assert "core_goal" in names
        assert "known_issue" in names

    def test_duplicate_type_names_raises(self, goal_type):
        with pytest.raises(ValueError):
            GroupDef(name="dup", node_types=[goal_type, goal_type])

    def test_is_valid_status(self, sample_group):
        assert sample_group.is_valid_status("core_goal", "active") is True
        assert sample_group.is_valid_status("core_goal", "resolved") is False

    def test_is_valid_status_unknown_type_raises(self, sample_group):
        with pytest.raises(KeyError):
            sample_group.is_valid_status("ghost", "active")

    def test_default_status_for_type(self, sample_group):
        assert sample_group.default_status("core_goal") == "active"

    def test_singletons_property(self, sample_group):
        assert "core_goal" in sample_group.singletons
        assert "known_issue" not in sample_group.singletons


# ── validate_node_metadata ────────────────────────────────────────────────────

class TestValidateNodeMetadata:
    def test_valid_metadata_returns_no_errors(self, goal_type):
        errors = validate_node_metadata(goal_type, {"agent": "claude", "priority": "high"})
        assert errors == []

    def test_empty_metadata_uses_defaults(self, goal_type):
        errors = validate_node_metadata(goal_type, {})
        assert errors == []

    def test_unknown_field_returns_error(self, goal_type):
        errors = validate_node_metadata(goal_type, {"unknown_field": "x"})
        assert any("unknown_field" in e for e in errors)

    def test_wrong_literal_value_returns_error(self, goal_type):
        errors = validate_node_metadata(goal_type, {"priority": "extreme"})
        assert any("priority" in e for e in errors)

    def test_wrong_type_returns_error(self, issue_type):
        errors = validate_node_metadata(issue_type, {"severity": 99})
        assert any("severity" in e for e in errors)

    def test_returns_list_of_strings(self, goal_type):
        errors = validate_node_metadata(goal_type, {"agent": "ok"})
        assert isinstance(errors, list)
        for e in errors:
            assert isinstance(e, str)
