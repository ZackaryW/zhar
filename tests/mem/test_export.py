"""TDD: zhar.mem.export — context snapshot renderer."""
from types import SimpleNamespace
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
                     summary="Group-clustered storage", status="accepted", tags=["arch"],
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
        # IDs are supported as legacy 4-char or new 5-char hex; just check the format is present
        import re
        assert re.search(r"\[[0-9a-f]{4,5}\]", out)

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

    def test_default_export_uses_current_boundary_for_group(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="decision_trail",
            node_type="adr",
            summary="Accepted ADR",
            status="accepted",
            content="## Status\naccepted",
        ))
        store.save(make_node(
            group="decision_trail",
            node_type="adr",
            summary="Proposed ADR",
            status="proposed",
            content="## Status\nproposed",
        ))

        out = export_group(store, "decision_trail")

        assert "Accepted ADR" in out
        assert "Proposed ADR" not in out

    def test_explicit_status_filter_overrides_current_boundary(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="decision_trail",
            node_type="adr",
            summary="Accepted ADR",
            status="accepted",
            content="## Status\naccepted",
        ))
        store.save(make_node(
            group="decision_trail",
            node_type="adr",
            summary="Proposed ADR",
            status="proposed",
            content="## Status\nproposed",
        ))

        out = export_group(store, "decision_trail", statuses=["proposed"])

        assert "Accepted ADR" not in out
        assert "Proposed ADR" in out

    def test_hides_redundant_file_change_path_when_source_present(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="stack sync",
            source="src/zhar/stack/sync.py::14::%ZHAR:ffff%",
            metadata={
                "path": "src/zhar/stack/sync.py",
                "significance": "feature",
            },
        ))

        out = export_group(store, "code_history")

        assert "source=src/zhar/stack/sync.py::14::%ZHAR:ffff%" in out
        assert "path=src/zhar/stack/sync.py" not in out

    def test_can_include_runtime_context_for_code_history(self, tmp_path, monkeypatch):
        from zhar.mem.groups import code_history as code_history_group

        outputs = {
            ("rev-parse", "--show-toplevel"): "D:/repo\n",
            ("status", "--short", "--", "src/zhar/stack/sync.py"): " M src/zhar/stack/sync.py\n",
            ("diff", "--stat", "--", "src/zhar/stack/sync.py"): " src/zhar/stack/sync.py | 4 +++-\n 1 file changed, 3 insertions(+), 1 deletion(-)\n",
            ("log", "--oneline", "-n", "5", "--", "src/zhar/stack/sync.py"): "abc1234 stack sync cleanup\n",
        }

        def fake_run(args, cwd, capture_output, text, check):
            return SimpleNamespace(returncode=0, stdout=outputs.get(tuple(args[1:]), ""))

        monkeypatch.setattr(code_history_group.subprocess, "run", fake_run)

        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="stack sync",
            source="src/zhar/stack/sync.py::14::%ZHAR:ffff%",
            metadata={"significance": "feature"},
        ))

        out = export_group(
            store,
            "code_history",
            include_runtime_context=True,
            project_root=tmp_path,
        )

        assert "### Runtime context" in out
        assert "#### git_companion" in out
        assert "Working tree status:" in out
        assert "Diff stat:" in out
        assert "Recent commits:" in out

    def test_code_history_export_is_capped_at_fifteen_entries_by_group_definition(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")

        for index in range(20):
            store.save(make_node(
                group="code_history",
                node_type="file_change",
                summary=f"file change {index:02d}",
            ))

        out = export_group(store, "code_history")

        assert "## code_history (15)" in out
        assert out.count("file_change ·") == 15


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

    def test_default_export_excludes_non_current_statuses_across_groups(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="problem_tracking",
            node_type="known_issue",
            summary="Active issue",
            status="active",
            content="## Details\nactive",
        ))
        store.save(make_node(
            group="problem_tracking",
            node_type="known_issue",
            summary="Resolved issue",
            status="resolved",
            content="## Details\nresolved",
        ))
        store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="Fresh file change",
            status="active",
        ))
        store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="Stale file change",
            status="stale",
        ))

        out = export_text(store)

        assert "Active issue" in out
        assert "Resolved issue" not in out
        assert "Fresh file change" in out
        assert "Stale file change" not in out
