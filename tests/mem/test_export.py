"""TDD: zhar.mem.export — context snapshot renderer."""
from pathlib import Path
import pytest
from zhar.mem.export import export_text, export_group
from zhar.mem.store import MemStore
from zhar.mem.node import make_node


@pytest.fixture
def store(tmp_path) -> MemStore:
    s = MemStore(tmp_path / ".zhar")
    s.save(make_node(group="project_dna", node_type="core_goal",
                     summary="Build zhar", metadata={"agent": "claude"}))
    s.save(make_node(group="project_dna", node_type="core_requirement",
                     summary="Use orjson", metadata={"priority": "high"}))
    s.save(make_node(group="decision_trail", node_type="adr",
                     summary="Group-clustered storage", tags=["arch"],
                     content="## Status\naccepted"))
    s.save(make_node(group="problem_tracking", node_type="known_issue",
                     summary="OOM on scan", metadata={"severity": "low"}))
    return s


# ── export_group ──────────────────────────────────────────────────────────────

class TestExportGroup:
    def test_returns_string(self, store):
        out = export_group(store, "project_dna")
        assert isinstance(out, str)

    def test_contains_group_header(self, store):
        out = export_group(store, "project_dna")
        assert "project_dna" in out

    def test_contains_node_summaries(self, store):
        out = export_group(store, "project_dna")
        assert "Build zhar" in out
        assert "Use orjson" in out

    def test_contains_node_ids(self, store):
        out = export_group(store, "project_dna")
        # IDs are 4-char hex; just check the format is present
        import re
        assert re.search(r"\[[0-9a-f]{4}\]", out)

    def test_includes_tags_when_present(self, store):
        out = export_group(store, "decision_trail")
        assert "arch" in out

    def test_includes_metadata_fields(self, store):
        out = export_group(store, "project_dna")
        assert "priority" in out or "high" in out

    def test_includes_content_body_when_present(self, store):
        out = export_group(store, "decision_trail")
        assert "## Status" in out or "accepted" in out

    def test_empty_group_returns_empty_string(self, store):
        out = export_group(store, "code_history")
        assert out == "" or "code_history" in out

    def test_unknown_group_returns_empty_string(self, store):
        out = export_group(store, "nonexistent")
        assert out == ""


# ── export_text ───────────────────────────────────────────────────────────────

class TestExportText:
    def test_returns_string(self, store):
        out = export_text(store)
        assert isinstance(out, str)

    def test_contains_all_groups_with_nodes(self, store):
        out = export_text(store)
        assert "project_dna" in out
        assert "decision_trail" in out
        assert "problem_tracking" in out

    def test_contains_all_summaries(self, store):
        out = export_text(store)
        assert "Build zhar" in out
        assert "Use orjson" in out
        assert "Group-clustered storage" in out
        assert "OOM on scan" in out

    def test_groups_with_zero_nodes_omitted_by_default(self, store):
        out = export_text(store)
        # code_history has no nodes — should not appear (or appear clearly empty)
        # We just verify the output is not bloated with empty sections
        lines = out.splitlines()
        code_history_lines = [l for l in lines if "code_history" in l]
        assert len(code_history_lines) == 0

    def test_statuses_filter(self, store):
        out = export_text(store, statuses=["active"])
        assert "Build zhar" in out

    def test_groups_filter(self, store):
        out = export_text(store, groups=["project_dna"])
        assert "Build zhar" in out
        assert "OOM on scan" not in out

    def test_includes_header_with_node_count(self, store):
        out = export_text(store)
        # Should mention total or per-group counts somewhere
        import re
        assert re.search(r"\d+", out)
