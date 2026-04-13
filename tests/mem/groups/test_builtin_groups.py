"""TDD: all four built-in groups expose valid GroupDef instances."""
import pytest
from zhar.mem.group import GroupDef, validate_node_metadata


@pytest.fixture(params=[
    "zhar.mem.groups.project_dna",
    "zhar.mem.groups.problem_tracking",
    "zhar.mem.groups.decision_trail",
    "zhar.mem.groups.code_history",
])
def builtin_group(request):
    import importlib
    mod = importlib.import_module(request.param)
    return mod.GROUP


class TestBuiltinGroups:
    def test_is_groupdef(self, builtin_group):
        assert isinstance(builtin_group, GroupDef)

    def test_has_name(self, builtin_group):
        assert builtin_group.name

    def test_has_at_least_one_node_type(self, builtin_group):
        assert len(builtin_group.node_types) >= 1

    def test_all_types_have_valid_statuses(self, builtin_group):
        for nt in builtin_group.node_types:
            assert len(nt.valid_statuses) >= 1

    def test_all_types_default_status_in_valid(self, builtin_group):
        for nt in builtin_group.node_types:
            assert nt.default_status in nt.valid_statuses

    def test_empty_metadata_validates_clean(self, builtin_group):
        for nt in builtin_group.node_types:
            errors = validate_node_metadata(nt, {})
            assert errors == [], f"{builtin_group.name}.{nt.name}: {errors}"

    def test_agent_field_present_on_all_types(self, builtin_group):
        """Every node type's meta_cls should have an 'agent' field."""
        import dataclasses
        for nt in builtin_group.node_types:
            field_names = [f.name for f in dataclasses.fields(nt.meta_cls)]
            assert "agent" in field_names, (
                f"{builtin_group.name}.{nt.name} missing 'agent' metadata field"
            )

    def test_runtime_context_provider_list_present(self, builtin_group):
        assert isinstance(builtin_group.runtime_context_providers, list)


class TestProjectDna:
    def test_core_goal_is_singleton(self):
        from zhar.mem.groups.project_dna import GROUP
        assert "core_goal" in GROUP.singletons

    def test_has_expected_types(self):
        from zhar.mem.groups.project_dna import GROUP
        expected = {"core_goal", "core_requirement", "product_context", "stakeholder"}
        assert expected == set(GROUP.type_names)

    def test_priority_literal_on_requirement(self):
        from zhar.mem.groups.project_dna import GROUP
        nt = GROUP.get_type("core_requirement")
        errors = validate_node_metadata(nt, {"priority": "high"})
        assert errors == []
        errors = validate_node_metadata(nt, {"priority": "extreme"})
        assert errors  # should fail


class TestProblemTracking:
    def test_has_expected_types(self):
        from zhar.mem.groups.problem_tracking import GROUP
        assert "known_issue" in GROUP.type_names
        assert "blocked" in GROUP.type_names

    def test_severity_literal(self):
        from zhar.mem.groups.problem_tracking import GROUP
        nt = GROUP.get_type("known_issue")
        assert validate_node_metadata(nt, {"severity": "critical"}) == []
        assert validate_node_metadata(nt, {"severity": "extreme"})


class TestDecisionTrail:
    def test_adr_starts_as_proposed(self):
        from zhar.mem.groups.decision_trail import GROUP
        assert GROUP.default_status("adr") == "proposed"

    def test_research_finding_outcome_literal(self):
        from zhar.mem.groups.decision_trail import GROUP
        nt = GROUP.get_type("research_finding")
        assert validate_node_metadata(nt, {"outcome": "adopted"}) == []
        assert validate_node_metadata(nt, {"outcome": "maybe"})


class TestCodeHistory:
    def test_has_expected_types(self):
        from zhar.mem.groups.code_history import GROUP
        expected = {"file_change", "function_change", "breaking_change", "revert_note"}
        assert expected == set(GROUP.type_names)

    def test_significance_literal(self):
        from zhar.mem.groups.code_history import GROUP
        nt = GROUP.get_type("file_change")
        assert validate_node_metadata(nt, {"significance": "breaking"}) == []
        assert validate_node_metadata(nt, {"significance": "typo"})

    def test_git_companion_provider_registered(self):
        from zhar.mem.groups.code_history import GROUP
        names = [provider.name for provider in GROUP.runtime_context_providers]
        assert "git_companion" in names
