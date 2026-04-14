"""TDD: zhar.mem.loader — group discovery from mem_*.py files."""
from dataclasses import dataclass
from pathlib import Path
import pytest
from zhar.mem.group import GroupDef, NodeTypeDef
from zhar.mem.loader import discover_groups, load_builtin_groups, load_all_groups


# ── helpers ───────────────────────────────────────────────────────────────────

def write_group_file(cfg_dir: Path, name: str, content: str) -> Path:
    f = cfg_dir / f"mem_{name}.py"
    f.write_text(content)
    return f


MINIMAL_GROUP_SRC = """\
from dataclasses import dataclass
from zhar.mem.group import GroupDef, NodeTypeDef

@dataclass
class PaymentMeta:
    currency: str = "USD"

GROUP = GroupDef(
    name="payments",
    node_types=[
        NodeTypeDef("payment_flow", PaymentMeta, valid_statuses=["active", "archived"]),
    ],
)
"""

MISSING_GROUP_VAR_SRC = """\
# No GROUP variable — should be skipped or raise
x = 1
"""

INVALID_GROUP_TYPE_SRC = """\
# GROUP is not a GroupDef — should raise
GROUP = "not-a-group-def"
"""


# ── discover_groups ───────────────────────────────────────────────────────────

class TestDiscoverGroups:
    def test_returns_empty_dict_for_empty_dir(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        result = discover_groups(cfg_dir)
        assert result == {}

    def test_discovers_valid_group_file(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        write_group_file(cfg_dir, "payments", MINIMAL_GROUP_SRC)
        result = discover_groups(cfg_dir)
        assert "payments" in result

    def test_discovered_group_is_groupdef(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        write_group_file(cfg_dir, "payments", MINIMAL_GROUP_SRC)
        result = discover_groups(cfg_dir)
        assert isinstance(result["payments"], GroupDef)

    def test_ignores_non_mem_prefixed_files(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "other.py").write_text("GROUP = None")
        (cfg_dir / "mem.py").write_text("GROUP = None")  # needs underscore
        result = discover_groups(cfg_dir)
        assert result == {}

    def test_ignores_non_python_files(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        (cfg_dir / "mem_stuff.toml").write_text("[section]")
        result = discover_groups(cfg_dir)
        assert result == {}

    def test_missing_group_var_raises_import_error(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        write_group_file(cfg_dir, "bad", MISSING_GROUP_VAR_SRC)
        with pytest.raises(ImportError):
            discover_groups(cfg_dir)

    def test_wrong_group_type_raises_type_error(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        write_group_file(cfg_dir, "bad", INVALID_GROUP_TYPE_SRC)
        with pytest.raises(TypeError):
            discover_groups(cfg_dir)

    def test_multiple_group_files(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        write_group_file(cfg_dir, "payments", MINIMAL_GROUP_SRC)
        write_group_file(cfg_dir, "deployments", MINIMAL_GROUP_SRC.replace(
            'name="payments"', 'name="deployments"'
        ))
        result = discover_groups(cfg_dir)
        assert len(result) == 2

    def test_nonexistent_dir_returns_empty(self, tmp_path):
        result = discover_groups(tmp_path / "does_not_exist")
        assert result == {}


# ── load_builtin_groups ───────────────────────────────────────────────────────

class TestLoadBuiltinGroups:
    def test_returns_dict(self):
        result = load_builtin_groups()
        assert isinstance(result, dict)

    def test_contains_all_builtin_groups(self):
        result = load_builtin_groups()
        for name in (
            "project_dna",
            "problem_tracking",
            "decision_trail",
            "architecture_context",
            "code_history",
            "notes",
        ):
            assert name in result, f"Missing built-in group: {name}"

    def test_all_values_are_groupdefs(self):
        result = load_builtin_groups()
        for name, g in result.items():
            assert isinstance(g, GroupDef), f"{name} is not a GroupDef"


# ── load_all_groups ───────────────────────────────────────────────────────────

class TestLoadAllGroups:
    def test_includes_builtins(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        result = load_all_groups(cfg_dir)
        assert "project_dna" in result

    def test_user_group_overrides_builtin_with_same_name(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        # Override project_dna with a custom version
        custom = MINIMAL_GROUP_SRC.replace(
            'name="payments"', 'name="project_dna"'
        )
        write_group_file(cfg_dir, "project_dna", custom)
        result = load_all_groups(cfg_dir)
        # Should use the custom version (has "payment_flow" type)
        assert "payment_flow" in result["project_dna"].type_names

    def test_user_groups_merged_with_builtins(self, tmp_path):
        cfg_dir = tmp_path / "cfg"
        cfg_dir.mkdir()
        write_group_file(cfg_dir, "payments", MINIMAL_GROUP_SRC)
        result = load_all_groups(cfg_dir)
        assert "payments" in result
        assert "project_dna" in result
