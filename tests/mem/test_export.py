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

    def test_tags_filter_limits_group_export_to_matching_nodes(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="project_dna",
            node_type="core_requirement",
            summary="Web requirement",
            tags=["project:web"],
            content="## Why\n\nWeb only.",
        ))
        store.save(make_node(
            group="project_dna",
            node_type="core_requirement",
            summary="API requirement",
            tags=["project:api"],
            content="## Why\n\nAPI only.",
        ))

        out = export_group(store, "project_dna", tags=["project:web"])

        assert "Web requirement" in out
        assert "API requirement" not in out

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

    def test_relation_depth_does_not_pull_component_rel_nodes_into_unrelated_exports(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="project_dna",
            node_type="core_requirement",
            summary="Web requirement",
            tags=["project:web"],
            content="## Why\n\nNeeded.",
        ))
        store.save(make_node(
            group="architecture_context",
            node_type="component_rel",
            summary="web -> api",
            tags=["project:web"],
            metadata={
                "from_component": "web",
                "to_component": "api",
                "rel_type": "calls",
            },
        ))
        store.save(make_node(
            group="architecture_context",
            node_type="component_rel",
            summary="api -> db",
            tags=["project:web"],
            metadata={
                "from_component": "api",
                "to_component": "db",
                "rel_type": "calls",
            },
        ))

        out = export_group(
            store,
            "project_dna",
            tags=["project:web"],
            relation_depth=1,
        )

        assert "Web requirement" in out
        assert "api -> db" not in out
        assert "web -> api" not in out

    def test_relation_depth_expands_across_built_in_links_group(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        source = store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="cli export wiring",
            tags=["project:web"],
        ))
        target = store.save(make_node(
            group="decision_trail",
            node_type="decision",
            summary="Export should include linked decision context",
            tags=["project:api"],
        ))
        store.save(make_node(
            group="links",
            node_type="node_link",
            summary="file change -> decision",
            metadata={
                "from_id": source.id,
                "to_id": target.id,
                "rel_type": "explains",
            },
        ))

        out = export_text(store, groups=["code_history"], tags=["project:web"], relation_depth=1)

        assert "cli export wiring" in out
        assert "Export should include linked decision context" not in out

    def test_relation_depth_silently_ignores_absent_link_nodes(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="cli export wiring",
        ))

        out = export_text(store, groups=["code_history"], relation_depth=1)

        assert "cli export wiring" in out

    def test_relation_depth_expands_across_built_in_links_group_with_matching_tags(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        source = store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="cli export wiring",
            tags=["project:web"],
        ))
        target = store.save(make_node(
            group="decision_trail",
            node_type="decision",
            summary="Export should include linked decision context",
            tags=["project:web"],
        ))
        store.save(make_node(
            group="links",
            node_type="node_link",
            summary="file change -> decision",
            metadata={
                "from_id": source.id,
                "to_id": target.id,
                "rel_type": "explains",
            },
        ))

        out = export_text(store, groups=["code_history"], tags=["project:web"], relation_depth=1)

        assert "cli export wiring" in out
        assert "Export should include linked decision context" in out

    def test_relation_depth_respects_tag_boundary_for_linked_nodes(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        source = store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="cli export wiring",
            tags=["project:web"],
        ))
        target = store.save(make_node(
            group="decision_trail",
            node_type="decision",
            summary="linked decision",
            tags=["project:api"],
        ))
        store.save(make_node(
            group="links",
            node_type="node_link",
            summary="file change -> decision",
            metadata={
                "from_id": source.id,
                "to_id": target.id,
                "rel_type": "explains",
            },
        ))
        out = export_text(store, groups=["code_history"], tags=["project:web"], relation_depth=1)

        assert "cli export wiring" in out
        assert "linked decision" not in out

    def test_relation_depth_skips_dangling_links_silently(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        source = store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="cli export wiring",
        ))
        target = store.save(make_node(
            group="decision_trail",
            node_type="decision",
            summary="linked decision",
        ))
        link = store.save(make_node(
            group="links",
            node_type="node_link",
            summary="file change -> decision",
            metadata={
                "from_id": source.id,
                "to_id": target.id,
                "rel_type": "explains",
            },
        ))
        store.delete(target.id)

        out = export_text(store, groups=["code_history"], relation_depth=1)

        assert "cli export wiring" in out
        assert "linked decision" not in out


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

    def test_tags_filter_limits_export_to_matching_nodes(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="project_dna",
            node_type="core_requirement",
            summary="Web requirement",
            tags=["project:web"],
            content="## Why\n\nWeb only.",
        ))
        store.save(make_node(
            group="problem_tracking",
            node_type="known_issue",
            summary="API issue",
            tags=["project:api"],
            content="## Details\n\nAPI only.",
        ))

        out = export_text(store, tags=["project:web"])

        assert "Web requirement" in out
        assert "API issue" not in out

    def test_tags_filter_can_produce_empty_export(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        store.save(make_node(
            group="project_dna",
            node_type="core_requirement",
            summary="Web requirement",
            tags=["project:web"],
            content="## Why\n\nWeb only.",
        ))

        out = export_text(store, tags=["project:api"])

        assert out == "# zhar memory — 0 nodes\n"

    def test_relation_depth_expands_linked_nodes_in_full_export(self, tmp_path):
        store = MemStore(tmp_path / ".zhar")
        source = store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="cli export wiring",
            tags=["project:web"],
        ))
        target = store.save(make_node(
            group="decision_trail",
            node_type="decision",
            summary="linked decision context",
            tags=["project:web"],
        ))
        store.save(make_node(
            group="links",
            node_type="node_link",
            summary="file change -> decision",
            metadata={
                "from_id": source.id,
                "to_id": target.id,
                "rel_type": "explains",
            },
        ))

        out = export_text(store, tags=["project:web"], relation_depth=1)

        assert "cli export wiring" in out
        assert "linked decision context" in out

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
