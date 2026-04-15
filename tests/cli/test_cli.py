"""TDD: zhar CLI commands — init, add, mutation, query, and status."""
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from pathlib import Path
import pytest
from click.testing import CliRunner

from zhar.cli import cli
from zhar.mem.node import make_node
from zhar.mem.store import MemStore
from zhar.mem_session.model import SessionData, SessionNodeState
from zhar.mem_session.store import save_session
from zhar.utils.times import format_dt


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def project(tmp_path, runner):
    """Initialised project dir."""
    result = runner.invoke(cli, ["--root", str(tmp_path), "init"])
    assert result.exit_code == 0, result.output
    return tmp_path


# ── init ──────────────────────────────────────────────────────────────────────

class TestInit:
    def test_creates_zhar_dir(self, tmp_path, runner):
        runner.invoke(cli, ["--root", str(tmp_path), "init"])
        assert (tmp_path / "mem").exists()

    def test_creates_gitignore_entry(self, tmp_path, runner):
        result = runner.invoke(cli, ["--root", str(tmp_path), "init"])
        # gitignore is written in the project root (parent of .zhar root)
        # gitignore coverage is handled thoroughly in test_fs; here just
        # verify init succeeded without error
        assert result.exit_code == 0

    def test_init_is_idempotent(self, tmp_path, runner):
        runner.invoke(cli, ["--root", str(tmp_path), "init"])
        result = runner.invoke(cli, ["--root", str(tmp_path), "init"])
        assert result.exit_code == 0


class TestHelp:
    def test_top_level_help_groups_commands_by_category(self, runner):
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0, result.output
        assert "Memory Commands:" in result.output
        assert "Facts Commands:" in result.output
        assert "Session Commands:" in result.output
        assert "Agent Commands:" in result.output
        assert "Harness Commands:" in result.output
        assert "Stack Commands:" in result.output
        assert "  add     " in result.output
        assert "  add-note" in result.output
        assert "  set-status" in result.output
        assert "  remove    " in result.output
        assert "  prune     " in result.output
        assert "  facts  " in result.output
        assert "  session" in result.output
        assert "  install    " in result.output
        assert "  harness" in result.output
        assert "  stack  " in result.output


# ── add ───────────────────────────────────────────────────────────────────────

class TestAdd:
    def test_add_prints_node_id(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Support pluggable backends",
        ])
        assert result.exit_code == 0, result.output
        # output should contain the new node ID
        import re
        assert re.search(r"Added [0-9a-f]{4,5}", result.output)

    def test_add_with_meta_fields(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "problem_tracking", "known_issue", "Redis OOM on large scan",
            "--meta", "severity=high",
            "--meta", "agent=claude",
        ])
        assert result.exit_code == 0, result.output

    def test_add_with_invalid_meta_value_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "problem_tracking", "known_issue", "Some bug",
            "--meta", "severity=catastrophic",  # not in Literal
        ])
        assert result.exit_code != 0
        assert "severity" in result.output.lower() or "catastrophic" in result.output.lower()

    def test_add_with_tags(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Must be fast",
            "--tag", "perf",
            "--tag", "backend",
        ])
        assert result.exit_code == 0, result.output

    def test_add_with_source(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "decision_trail", "adr", "Use orjson for serialisation",
            "--source", "src/zhar/mem/backends/json_backend.py",
        ])
        assert result.exit_code == 0, result.output

    def test_add_with_content_on_backed_type(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "decision_trail", "adr", "Use orjson",
            "--content", "## Context\n\nYAML was slow.",
        ])
        assert result.exit_code == 0, result.output

    def test_add_with_from_env_on_backed_type_sets_content(self, project, runner):
        result = runner.invoke(
            cli,
            [
                "--root", str(project), "add",
                "decision_trail", "adr", "Use orjson",
                "--from-env", "ZHAR_NOTE_BODY",
            ],
            env={"ZHAR_NOTE_BODY": "## Context\n\nYAML was slow."},
        )

        assert result.exit_code == 0, result.output
        node_id = __import__("re").search(r"Added ([0-9a-f]{4,5})", result.output).group(1)
        store = MemStore(project)
        node = store.get(node_id)
        assert node is not None
        assert node.content == "## Context\n\nYAML was slow."

    def test_add_with_from_env_on_non_backed_type_creates_attached_note(self, project, runner):
        result = runner.invoke(
            cli,
            [
                "--root", str(project), "add",
                "decision_trail", "decision", "Runtime workflow",
                "--from-env", "ZHAR_NOTE_BODY",
            ],
            env={"ZHAR_NOTE_BODY": "Runtime detail body."},
        )

        assert result.exit_code == 0, result.output
        import re
        node_id = re.search(r"Added ([0-9a-f]{4,5})", result.output).group(1)
        assert "Attached note" in result.output
        store = MemStore(project)
        notes = store.attached_notes(node_id)
        assert len(notes) == 1
        assert notes[0].content == "Runtime detail body."

    def test_add_with_content_var_alias_on_non_backed_type_creates_attached_note(self, project, runner):
        result = runner.invoke(
            cli,
            [
                "--root", str(project), "add",
                "decision_trail", "decision", "Runtime workflow alias",
                "--content-var", "ZHAR_NOTE_BODY_ALIAS_TEST",
            ],
            env={"ZHAR_NOTE_BODY_ALIAS_TEST": "Alias-backed runtime detail."},
        )

        assert result.exit_code == 0, result.output
        import re
        node_id = re.search(r"Added ([0-9a-f]{4,5})", result.output).group(1)
        notes = MemStore(project).attached_notes(node_id)
        assert len(notes) == 1
        assert notes[0].content == "Alias-backed runtime detail."

    def test_add_rejects_content_and_from_env_together(self, project, runner):
        result = runner.invoke(
            cli,
            [
                "--root", str(project), "add",
                "decision_trail", "adr", "Use orjson",
                "--content", "literal",
                "--from-env", "ZHAR_NOTE_BODY",
            ],
            env={"ZHAR_NOTE_BODY": "ignored"},
        )

        assert result.exit_code != 0
        assert "either CONTENT or --from-env" in result.output

    def test_add_content_on_non_backed_type_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_goal", "Ship it",
            "--content", "This should fail",
        ])
        assert result.exit_code != 0

    def test_add_unknown_group_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "nonexistent_group", "some_type", "summary",
        ])
        assert result.exit_code != 0

    def test_add_singleton_twice_exits_nonzero(self, project, runner):
        runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_goal", "First goal",
        ])
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_goal", "Second goal",
        ])
        assert result.exit_code != 0

    def test_meta_bad_syntax_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "A req",
            "--meta", "no-equals-sign",
        ])
        assert result.exit_code != 0


# ── note ──────────────────────────────────────────────────────────────────────

class TestNote:
    def _add_adr(self, project, runner) -> str:
        """Helper: add an ADR and return its ID."""
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "decision_trail", "adr", "Use orjson",
        ])
        assert result.exit_code == 0, result.output
        import re
        return re.search(r"Added ([0-9a-f]{4,5})", result.output).group(1)

    def test_note_sets_content(self, project, runner):
        nid = self._add_adr(project, runner)
        result = runner.invoke(cli, [
            "--root", str(project), "note", nid, "## Body\n\nDetails.",
        ])
        assert result.exit_code == 0, result.output

    def test_note_reads_content_from_stdin(self, project, runner):
        nid = self._add_adr(project, runner)
        result = runner.invoke(
            cli,
            ["--root", str(project), "note", nid, "-"],
            input="## Body\n\nFrom stdin.",
        )
        assert result.exit_code == 0, result.output

    def test_note_reads_content_from_env_var(self, project, runner):
        nid = self._add_adr(project, runner)
        result = runner.invoke(
            cli,
            ["--root", str(project), "note", nid, "--from-env", "ZHAR_NOTE_BODY_TEST"],
            env={"ZHAR_NOTE_BODY_TEST": "## Body\n\nFrom env."},
        )
        assert result.exit_code == 0, result.output

    def test_note_requires_content_or_env_var(self, project, runner):
        nid = self._add_adr(project, runner)
        result = runner.invoke(cli, ["--root", str(project), "note", nid])
        assert result.exit_code != 0
        assert "Missing CONTENT" in result.output

    def test_note_rejects_missing_env_var(self, project, runner):
        nid = self._add_adr(project, runner)
        result = runner.invoke(
            cli,
            ["--root", str(project), "note", nid, "--from-env", "ZHAR_NOTE_BODY_MISSING_TEST"],
        )
        assert result.exit_code != 0
        assert "is not set" in result.output

    def test_note_rejects_content_and_env_var_together(self, project, runner):
        nid = self._add_adr(project, runner)
        result = runner.invoke(
            cli,
            ["--root", str(project), "note", nid, "literal", "--from-env", "ZHAR_NOTE_BODY_CONFLICT_TEST"],
            env={"ZHAR_NOTE_BODY_CONFLICT_TEST": "ignored"},
        )
        assert result.exit_code != 0
        assert "either CONTENT or --from-env" in result.output

    def test_note_reads_content_from_content_var_alias(self, project, runner):
        nid = self._add_adr(project, runner)
        result = runner.invoke(
            cli,
            ["--root", str(project), "note", nid, "--content-var", "ZHAR_NOTE_BODY_ALIAS_NOTE_TEST"],
            env={"ZHAR_NOTE_BODY_ALIAS_NOTE_TEST": "## Body\n\nFrom alias."},
        )
        assert result.exit_code == 0, result.output

    def test_note_on_non_backed_type_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_goal", "A goal",
        ])
        import re
        nid = re.search(r"Added ([0-9a-f]{4,5})", result.output).group(1)
        result2 = runner.invoke(cli, [
            "--root", str(project), "note", nid, "Some content",
        ])
        assert result2.exit_code != 0

    def test_note_unknown_id_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "note", "zzzz", "content",
        ])
        assert result.exit_code != 0


class TestAddNote:
    def test_add_note_reads_content_from_env_var(self, project, runner):
        store = MemStore(project)
        base = make_node(
            group="decision_trail",
            node_type="decision",
            summary="Runtime workflow",
        )
        store.save(base)

        result = runner.invoke(
            cli,
            ["--root", str(project), "add-note", base.id, "--from-env", "ZHAR_NOTE_BODY"],
            env={"ZHAR_NOTE_BODY": "Supplemental detail."},
        )

        assert result.exit_code == 0, result.output
        notes = MemStore(project).attached_notes(base.id)
        assert len(notes) == 1
        assert notes[0].content == "Supplemental detail."

    def test_add_note_reads_content_from_content_var_alias(self, project, runner):
        store = MemStore(project)
        base = make_node(
            group="decision_trail",
            node_type="decision",
            summary="Runtime workflow alias",
        )
        store.save(base)

        result = runner.invoke(
            cli,
            ["--root", str(project), "add-note", base.id, "--content-var", "ZHAR_ADD_NOTE_ALIAS_TEST"],
            env={"ZHAR_ADD_NOTE_ALIAS_TEST": "Supplemental detail from alias."},
        )

        assert result.exit_code == 0, result.output
        notes = MemStore(project).attached_notes(base.id)
        assert len(notes) == 1
        assert notes[0].content == "Supplemental detail from alias."


class TestAddNote:
    def _add_requirement(self, project, runner, summary: str = "Must support TDD") -> str:
        """Helper: add a requirement and return its node ID."""
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", summary,
            "--content", "## Why\n\nBecause.",
        ])
        assert result.exit_code == 0, result.output
        import re
        return re.search(r"Added ([0-9a-f]{4,5})", result.output).group(1)

    def test_add_note_creates_attached_note(self, project, runner):
        target_id = self._add_requirement(project, runner)

        result = runner.invoke(cli, [
            "--root", str(project), "add-note", target_id, "Extra implementation context.",
        ])

        assert result.exit_code == 0, result.output
        store = MemStore(project)
        notes = store.query(__import__("zhar.mem.query", fromlist=["Query"]).Query(groups=["notes"]))
        assert len(notes) == 1
        assert notes[0].metadata["target_ids"] == target_id
        assert notes[0].content == "Extra implementation context."

    def test_add_note_supports_multiple_targets(self, project, runner):
        first_id = self._add_requirement(project, runner, "First target")
        second_id = self._add_requirement(project, runner, "Second target")

        result = runner.invoke(cli, [
            "--root", str(project), "add-note", first_id, "Shared note.", "--target", second_id,
        ])

        assert result.exit_code == 0, result.output
        store = MemStore(project)
        notes = store.query(__import__("zhar.mem.query", fromlist=["Query"]).Query(groups=["notes"]))
        assert len(notes) == 1
        assert notes[0].metadata["target_ids"] == f"{first_id},{second_id}"

    def test_add_note_rejects_unknown_target(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add-note", "zzzz", "Extra implementation context.",
        ])

        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "does not exist" in result.output.lower()

    def test_add_note_rejects_note_target(self, project, runner):
        target_id = self._add_requirement(project, runner)
        create_result = runner.invoke(cli, [
            "--root", str(project), "add-note", target_id, "First note.",
        ])
        assert create_result.exit_code == 0, create_result.output

        store = MemStore(project)
        note_id = store.query(__import__("zhar.mem.query", fromlist=["Query"]).Query(groups=["notes"]))[0].id

        result = runner.invoke(cli, [
            "--root", str(project), "add-note", note_id, "Nested note.",
        ])

        assert result.exit_code != 0
        assert "cannot target other note nodes" in result.output.lower()


# ── show ──────────────────────────────────────────────────────────────────────

class TestShow:
    def test_show_displays_summary(self, project, runner):
        add = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Must support TDD",
        ])
        import re
        nid = re.search(r"Added ([0-9a-f]{4,5})", add.output).group(1)
        result = runner.invoke(cli, ["--root", str(project), "show", nid])
        assert result.exit_code == 0, result.output
        assert "Must support TDD" in result.output

    def test_show_displays_group_and_type(self, project, runner):
        add = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "A requirement",
        ])
        import re
        nid = re.search(r"Added ([0-9a-f]{4,5})", add.output).group(1)
        result = runner.invoke(cli, ["--root", str(project), "show", nid])
        assert "project_dna" in result.output
        assert "core_requirement" in result.output

    def test_show_does_not_expand_component_rel_nodes_without_links(self, project, runner):
        store = MemStore(project)
        base = make_node(
            group="architecture_context",
            node_type="component_rel",
            summary="web -> api",
            tags=["project:web"],
            metadata={
                "from_component": "web",
                "to_component": "api",
                "rel_type": "calls",
            },
        )
        store.save(base)
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
        store.save(make_node(
            group="architecture_context",
            node_type="component_rel",
            summary="api -> shared-db",
            tags=["project:api"],
            metadata={
                "from_component": "api",
                "to_component": "shared-db",
                "rel_type": "calls",
            },
        ))

        result = runner.invoke(cli, [
            "--root", str(project), "show", base.id, "--relation-depth", "1",
        ])

        assert result.exit_code == 0, result.output
        assert "web -> api" in result.output
        assert "api -> db" not in result.output
        assert "api -> shared-db" not in result.output

    def test_show_relation_depth_is_noop_for_non_relation_nodes(self, project, runner):
        add = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "A requirement",
            "--content", "## Why\n\nNeeded.",
        ])
        import re
        nid = re.search(r"Added ([0-9a-f]{4,5})", add.output).group(1)

        result = runner.invoke(cli, [
            "--root", str(project), "show", nid, "--relation-depth", "2",
        ])

        assert result.exit_code == 0, result.output
        assert "A requirement" in result.output
        assert "related nodes" not in result.output.lower()

    def test_show_can_expand_related_nodes_through_built_in_links_group(self, project, runner):
        store = MemStore(project)
        base = store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="cli export wiring",
        ))
        target = store.save(make_node(
            group="decision_trail",
            node_type="decision",
            summary="Linked decision context",
        ))
        store.save(make_node(
            group="links",
            node_type="node_link",
            summary="file change -> decision",
            metadata={
                "from_id": base.id,
                "to_id": target.id,
                "rel_type": "explains",
            },
        ))

        result = runner.invoke(cli, [
            "--root", str(project), "show", base.id, "--relation-depth", "1",
        ])

        assert result.exit_code == 0, result.output
        assert "cli export wiring" in result.output
        assert "Linked decision context" in result.output

    def test_show_unknown_id_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, ["--root", str(project), "show", "zzzz"])
        assert result.exit_code != 0

    def test_show_can_render_json(self, project, runner):
        add = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Must support TDD",
            "--content", "## Why\n\nNeeded.",
            "--tag", "quality",
        ])
        import re
        nid = re.search(r"Added ([0-9a-f]{4,5})", add.output).group(1)

        result = runner.invoke(cli, ["--root", str(project), "show", nid, "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["node"]["id"] == nid
        assert payload["node"]["group"] == "project_dna"
        assert payload["node"]["node_type"] == "core_requirement"
        assert payload["node"]["summary"] == "Must support TDD"
        assert payload["node"]["content"] == "## Why\n\nNeeded."
        assert payload["node"]["tags"] == ["quality"]
        assert payload["related_nodes"] == []


class TestSetStatus:
    def _add_issue(self, project, runner) -> str:
        """Helper: add a known_issue node and return its ID."""
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "problem_tracking", "known_issue", "Broken status flow",
            "--content", "## Details\n\nNeeds a lifecycle.",
        ])
        assert result.exit_code == 0, result.output
        import re
        return re.search(r"Added ([0-9a-f]{4,5})", result.output).group(1)

    def test_set_status_updates_node(self, project, runner):
        nid = self._add_issue(project, runner)

        result = runner.invoke(cli, ["--root", str(project), "set-status", nid, "resolved"])

        assert result.exit_code == 0, result.output
        store = MemStore(project)
        assert store.get(nid).status == "resolved"

    def test_set_status_rejects_invalid_status(self, project, runner):
        nid = self._add_issue(project, runner)

        result = runner.invoke(cli, ["--root", str(project), "set-status", nid, "maybe"])

        assert result.exit_code != 0
        assert "Invalid status" in result.output

    def test_set_status_unknown_id_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, ["--root", str(project), "set-status", "zzzz", "resolved"])

        assert result.exit_code != 0
        assert "not found" in result.output


class TestRemove:
    def test_remove_deletes_node(self, project, runner):
        add = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Remove me",
            "--content", "## Why\n\nTemporary.",
        ])
        import re
        nid = re.search(r"Added ([0-9a-f]{4,5})", add.output).group(1)

        result = runner.invoke(cli, ["--root", str(project), "remove", nid])

        assert result.exit_code == 0, result.output
        store = MemStore(project)
        assert store.get(nid) is None

    def test_remove_unknown_id_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, ["--root", str(project), "remove", "zzzz"])

        assert result.exit_code != 0
        assert "not found" in result.output


class TestPrune:
    def _populate(self, project, runner) -> None:
        """Create nodes with distinct groups, tags, and statuses for prune tests."""
        issue = runner.invoke(cli, [
            "--root", str(project), "add",
            "problem_tracking", "known_issue", "Prunable issue",
            "--tag", "stale",
            "--content", "## Details\n\nCan be removed.",
        ])
        assert issue.exit_code == 0, issue.output
        import re
        issue_id = re.search(r"Added ([0-9a-f]{4,5})", issue.output).group(1)
        set_status = runner.invoke(cli, ["--root", str(project), "set-status", issue_id, "resolved"])
        assert set_status.exit_code == 0, set_status.output

        requirement = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Keep me",
            "--tag", "keep",
            "--content", "## Why\n\nStill needed.",
        ])
        assert requirement.exit_code == 0, requirement.output

    def test_prune_dry_run_reports_matches_without_deleting(self, project, runner):
        self._populate(project, runner)

        result = runner.invoke(cli, [
            "--root", str(project), "prune",
            "--group", "problem_tracking",
            "--status", "resolved",
            "--dry-run",
        ])

        assert result.exit_code == 0, result.output
        assert "[dry-run] Would remove 1 node(s)." in result.output
        store = MemStore(project)
        assert len(store.query(__import__("zhar.mem.query", fromlist=["Query"]).Query(groups=["problem_tracking"]))) == 1

    def test_prune_removes_matching_nodes(self, project, runner):
        self._populate(project, runner)

        result = runner.invoke(cli, [
            "--root", str(project), "prune",
            "--group", "problem_tracking",
            "--status", "resolved",
        ])

        assert result.exit_code == 0, result.output
        assert "Removed 1 node(s)." in result.output
        store = MemStore(project)
        assert len(store.query(__import__("zhar.mem.query", fromlist=["Query"]).Query(groups=["problem_tracking"]))) == 0
        assert len(store.query(__import__("zhar.mem.query", fromlist=["Query"]).Query(groups=["project_dna"]))) == 1

    def test_prune_requires_at_least_one_filter(self, project, runner):
        result = runner.invoke(cli, ["--root", str(project), "prune"])

        assert result.exit_code != 0
        assert "at least one filter" in result.output.lower()


# ── query ─────────────────────────────────────────────────────────────────────

class TestQuery:
    def _populate(self, project, runner):
        runner.invoke(cli, ["--root", str(project), "add",
                            "project_dna", "core_requirement", "Fast query engine",
                            "--tag", "perf"])
        runner.invoke(cli, ["--root", str(project), "add",
                            "problem_tracking", "known_issue", "Memory leak in scan",
                            "--meta", "severity=high"])

    def test_query_returns_results(self, project, runner):
        self._populate(project, runner)
        result = runner.invoke(cli, ["--root", str(project), "query"])
        assert result.exit_code == 0
        assert "Fast query engine" in result.output or "Memory leak" in result.output

    def test_query_filter_by_group(self, project, runner):
        self._populate(project, runner)
        result = runner.invoke(cli, [
            "--root", str(project), "query", "--group", "project_dna",
        ])
        assert result.exit_code == 0
        assert "Fast query engine" in result.output
        assert "Memory leak" not in result.output

    def test_query_filter_by_tag(self, project, runner):
        self._populate(project, runner)
        result = runner.invoke(cli, [
            "--root", str(project), "query", "--tag", "perf",
        ])
        assert result.exit_code == 0
        assert "Fast query engine" in result.output

    def test_query_text_search(self, project, runner):
        self._populate(project, runner)
        result = runner.invoke(cli, [
            "--root", str(project), "query", "--q", "memory leak",
        ])
        assert result.exit_code == 0
        assert "Memory leak" in result.output

    def test_query_no_results_exits_zero(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "query", "--q", "zzznomatch",
        ])
        assert result.exit_code == 0

    def test_query_can_render_json(self, project, runner):
        self._populate(project, runner)

        result = runner.invoke(cli, [
            "--root", str(project), "query", "--format", "json",
        ])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["count"] >= 2
        assert any(node["summary"] == "Fast query engine" for node in payload["nodes"])
        assert any(node["summary"] == "Memory leak in scan" for node in payload["nodes"])

    def test_query_json_can_include_attached_notes(self, project, runner):
        add = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Base requirement",
            "--content", "## Why\n\nBecause.",
        ])
        import re
        node_id = re.search(r"Added ([0-9a-f]{4,5})", add.output).group(1)
        note = runner.invoke(cli, [
            "--root", str(project), "add-note", node_id, "Supplemental note.",
        ])
        assert note.exit_code == 0, note.output

        result = runner.invoke(cli, [
            "--root", str(project), "query", "--format", "json", "--note-depth", "1",
        ])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        target = next(node for node in payload["nodes"] if node["id"] == node_id)
        assert len(target["notes"]) == 1
        assert target["notes"][0]["content"] == "Supplemental note."


# ── status ────────────────────────────────────────────────────────────────────

class TestStatus:
    def test_status_shows_all_groups(self, project, runner):
        result = runner.invoke(cli, ["--root", str(project), "status"])
        assert result.exit_code == 0
        assert "project_dna" in result.output
        assert "problem_tracking" in result.output
        assert "decision_trail" in result.output
        assert "code_history" in result.output

    def test_status_shows_counts_after_add(self, project, runner):
        runner.invoke(cli, ["--root", str(project), "add",
                            "project_dna", "core_requirement", "A req"])
        result = runner.invoke(cli, ["--root", str(project), "status"])
        assert result.exit_code == 0
        assert "1" in result.output  # at least one count shows 1

    def test_status_can_render_json(self, project, runner):
        runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "A req",
        ])

        result = runner.invoke(cli, ["--root", str(project), "status", "--format", "json"])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["total_nodes"] >= 1
        assert payload["groups"]["project_dna"]["total"] >= 1
        assert "core_requirement" in payload["groups"]["project_dna"]["by_type"]


class TestFacts:
    def test_facts_set_and_get_project_scope(self, project, runner):
        set_result = runner.invoke(cli, [
            "--root", str(project), "facts", "set", "runner", "pytest",
        ])
        get_result = runner.invoke(cli, [
            "--root", str(project), "facts", "get", "runner",
        ])

        assert set_result.exit_code == 0, set_result.output
        assert get_result.exit_code == 0, get_result.output
        assert get_result.output.strip() == "pytest"

    def test_facts_set_global_scope(self, project, runner, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("HOME", str(home))

        set_result = runner.invoke(cli, [
            "--root", str(project), "facts", "set", "--scope", "global", "package_manager", "uv",
        ])
        list_result = runner.invoke(cli, [
            "--root", str(project), "facts", "list", "--scope", "global",
        ])

        assert set_result.exit_code == 0, set_result.output
        assert list_result.exit_code == 0, list_result.output
        assert "package_manager = uv" in list_result.output

    def test_facts_get_effective_scope_prefers_project(self, project, runner, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("HOME", str(home))

        global_result = runner.invoke(cli, [
            "--root", str(project), "facts", "set", "--scope", "global", "runner", "pytest",
        ])
        project_result = runner.invoke(cli, [
            "--root", str(project), "facts", "set", "runner", "nox",
        ])
        get_result = runner.invoke(cli, [
            "--root", str(project), "facts", "get", "runner",
        ])

        assert global_result.exit_code == 0, global_result.output
        assert project_result.exit_code == 0, project_result.output
        assert get_result.exit_code == 0, get_result.output
        assert get_result.output.strip() == "nox"

    def test_facts_unset_global_scope(self, project, runner, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("HOME", str(home))

        runner.invoke(cli, [
            "--root", str(project), "facts", "set", "--scope", "global", "repo", "zhar",
        ])
        unset_result = runner.invoke(cli, [
            "--root", str(project), "facts", "unset", "--scope", "global", "repo",
        ])
        get_result = runner.invoke(cli, [
            "--root", str(project), "facts", "get", "--scope", "global", "repo",
        ])

        assert unset_result.exit_code == 0, unset_result.output
        assert get_result.exit_code != 0


class TestInstallCommand:
    def test_install_includes_effective_global_and_project_facts(self, project, runner, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("HOME", str(home))

        runner.invoke(cli, [
            "--root", str(project), "facts", "set", "--scope", "global", "package_manager", "uv",
        ])
        runner.invoke(cli, [
            "--root", str(project), "facts", "set", "primary_language", "python",
        ])

        output = project / "zhar.agent.md"
        result = runner.invoke(cli, [
            "--root", str(project), "install", "--out", str(output),
        ])

        assert result.exit_code == 0, result.output
        content = output.read_text(encoding="utf-8")
        assert "package_manager" in content
        assert "primary_language" in content


class TestExport:
    def test_export_can_render_json(self, project, runner):
        runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Web requirement",
            "--content", "## Why\n\nWeb only.",
            "--tag", "project:web",
        ])

        result = runner.invoke(cli, [
            "--root", str(project), "export", "--format", "json", "--tag", "project:web",
        ])

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["total_nodes"] == 1
        assert payload["groups"]["project_dna"]["count"] == 1
        assert payload["groups"]["project_dna"]["nodes"][0]["summary"] == "Web requirement"

    def test_export_can_include_transient_session_state(self, project, runner, monkeypatch):
        from zhar.mem_session import runtime as session_runtime_module

        session_dir = project / "tmp-session"
        monkeypatch.setattr(session_runtime_module, "default_session_dir", lambda: session_dir)

        store = MemStore(project)
        node = make_node(
            group="project_dna",
            node_type="core_requirement",
            summary="Inspect requirement",
            content="## Why\n\nTrack show state.",
        )
        store.save(node)

        show_result = runner.invoke(
            cli,
            ["--root", str(project), "show", node.id],
            env={"ZHAR_SESSION_ID": "session-one"},
        )
        export_result = runner.invoke(
            cli,
            ["--root", str(project), "export", "--with-runtime-context"],
            env={"ZHAR_SESSION_ID": "session-one"},
        )

        assert show_result.exit_code == 0, show_result.output
        assert export_result.exit_code == 0, export_result.output
        assert "### Session state" in export_result.output
        assert "session_id=session-one" in export_result.output
        assert f"- {node.id} state=shown score=1" in export_result.output

    def test_export_json_can_include_runtime_context(self, project, runner, monkeypatch):
        from zhar.mem_session import runtime as session_runtime_module

        session_dir = project / "tmp-session"
        monkeypatch.setattr(session_runtime_module, "default_session_dir", lambda: session_dir)

        store = MemStore(project)
        node = make_node(
            group="project_dna",
            node_type="core_requirement",
            summary="Inspect requirement",
            content="## Why\n\nTrack show state.",
        )
        store.save(node)

        show_result = runner.invoke(
            cli,
            ["--root", str(project), "show", node.id],
            env={"ZHAR_SESSION_ID": "session-one"},
        )
        export_result = runner.invoke(
            cli,
            ["--root", str(project), "export", "--format", "json", "--with-runtime-context"],
            env={"ZHAR_SESSION_ID": "session-one"},
        )

        assert show_result.exit_code == 0, show_result.output
        assert export_result.exit_code == 0, export_result.output
        payload = json.loads(export_result.output)
        assert payload["runtime_context"]["session"]["session_id"] == "session-one"
        assert payload["runtime_context"]["session"]["shown_nodes"] == 1
        assert payload["runtime_context"]["session"]["nodes"][0]["id"] == node.id

    def test_session_need_challenge_reports_suspicious_nodes_when_enabled(self, project, runner, monkeypatch):
        from zhar.mem_session import runtime as session_runtime_module

        session_dir = project / "tmp-session"
        monkeypatch.setattr(session_runtime_module, "default_session_dir", lambda: session_dir)

        now = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)
        save_session(
            SessionData(
                session_id="session-one",
                project_root=str(project.parent),
                cwd=str(project.parent),
                started_at=format_dt(now),
                updated_at=format_dt(now),
                nodes={
                    "353ca": SessionNodeState(
                        state="suspicious",
                        show_count=9,
                        expanded_count=1,
                        last_shown_at=format_dt(now),
                        last_expanded_at=format_dt(now),
                        last_scored_at=format_dt(now),
                        score=57,
                        status="suspicious",
                    )
                },
            ),
            base_dir=session_dir,
        )

        enabled_result = runner.invoke(cli, [
            "--root", str(project), "facts", "set", "session_challenge_enabled", "true",
        ])
        agent_result = runner.invoke(cli, [
            "--root", str(project), "facts", "set", "session_challenge_agent", "challenge-judge",
        ])
        result = runner.invoke(
            cli,
            ["--root", str(project), "session", "need-challenge"],
            env={"ZHAR_SESSION_ID": "session-one"},
        )

        assert enabled_result.exit_code == 0, enabled_result.output
        assert agent_result.exit_code == 0, agent_result.output
        assert result.exit_code == 0, result.output
        assert "353ca" in result.output
        assert "challenge-judge" in result.output

    def test_session_list_includes_saved_sessions_for_current_project(self, project, runner, monkeypatch):
        from zhar.mem_session import runtime as session_runtime_module

        session_dir = project / "tmp-session"
        monkeypatch.setattr(session_runtime_module, "default_session_dir", lambda: session_dir)

        now = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)
        save_session(
            SessionData(
                session_id="session-one",
                project_root=str(project.parent),
                cwd=str(project.parent),
                started_at=format_dt(now),
                updated_at=format_dt(now),
                nodes={
                    "353ca": SessionNodeState(
                        state="suspicious",
                        show_count=9,
                        expanded_count=1,
                        last_shown_at=format_dt(now),
                        last_expanded_at=format_dt(now),
                        last_scored_at=format_dt(now),
                        score=57,
                        status="suspicious",
                    )
                },
            ),
            base_dir=session_dir,
        )

        result = runner.invoke(cli, ["--root", str(project), "session", "list"])

        assert result.exit_code == 0, result.output
        assert "session-one" in result.output
        assert "suspicious=1" in result.output

    def test_session_current_reports_active_session_metadata(self, project, runner, monkeypatch):
        from zhar.mem_session import runtime as session_runtime_module

        session_dir = project / "tmp-session"
        monkeypatch.setattr(session_runtime_module, "default_session_dir", lambda: session_dir)

        now = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)
        save_session(
            SessionData(
                session_id="session-one",
                project_root=str(project.parent),
                cwd=str(project.parent),
                started_at=format_dt(now),
                updated_at=format_dt(now),
                challenge_enabled=True,
                nodes={
                    "353ca": SessionNodeState(
                        state="shown",
                        show_count=2,
                        expanded_count=0,
                        last_shown_at=format_dt(now),
                        last_scored_at=format_dt(now),
                        score=2,
                        status="normal",
                    )
                },
            ),
            base_dir=session_dir,
        )
        fact_result = runner.invoke(cli, [
            "--root", str(project), "facts", "set", "session_challenge_enabled", "true",
        ])
        assert fact_result.exit_code == 0, fact_result.output

        result = runner.invoke(
            cli,
            ["--root", str(project), "session", "current"],
            env={"ZHAR_SESSION_ID": "session-one"},
        )

        assert result.exit_code == 0, result.output
        assert "session_id=session-one" in result.output
        assert "enabled=true" in result.output
        assert "shown_nodes=1" in result.output

    def test_session_current_can_render_json(self, project, runner, monkeypatch):
        from zhar.mem_session import runtime as session_runtime_module

        session_dir = project / "tmp-session"
        monkeypatch.setattr(session_runtime_module, "default_session_dir", lambda: session_dir)

        now = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)
        save_session(
            SessionData(
                session_id="session-one",
                project_root=str(project.parent),
                cwd=str(project.parent),
                started_at=format_dt(now),
                updated_at=format_dt(now),
                challenge_enabled=True,
                nodes={
                    "353ca": SessionNodeState(
                        state="shown",
                        show_count=2,
                        expanded_count=0,
                        last_shown_at=format_dt(now),
                        last_scored_at=format_dt(now),
                        score=2,
                        status="normal",
                    )
                },
            ),
            base_dir=session_dir,
        )
        fact_result = runner.invoke(cli, [
            "--root", str(project), "facts", "set", "session_challenge_enabled", "true",
        ])
        assert fact_result.exit_code == 0, fact_result.output

        result = runner.invoke(
            cli,
            ["--root", str(project), "session", "current", "--format", "json"],
            env={"ZHAR_SESSION_ID": "session-one"},
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["session_id"] == "session-one"
        assert payload["enabled"] is True
        assert payload["shown_nodes"] == 1
        assert payload["challenge_enabled"] is True

    def test_session_clear_removes_active_session_file(self, project, runner, monkeypatch):
        from zhar.mem_session import runtime as session_runtime_module

        session_dir = project / "tmp-session"
        monkeypatch.setattr(session_runtime_module, "default_session_dir", lambda: session_dir)

        now = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)
        save_session(
            SessionData(
                session_id="session-one",
                project_root=str(project.parent),
                cwd=str(project.parent),
                started_at=format_dt(now),
                updated_at=format_dt(now),
                nodes={},
            ),
            base_dir=session_dir,
        )

        result = runner.invoke(
            cli,
            ["--root", str(project), "session", "clear"],
            env={"ZHAR_SESSION_ID": "session-one"},
        )

        assert result.exit_code == 0, result.output
        assert "Cleared session session-one" in result.output
        assert not (session_dir / "session-one.json").exists()

    def test_export_can_include_runtime_context(self, project, runner, monkeypatch):
        from zhar.mem.groups import code_history as code_history_group

        outputs = {
            ("rev-parse", "--show-toplevel"): "D:/repo\n",
            ("status", "--short", "--", "src/zhar/cli/memory.py"): " M src/zhar/cli/memory.py\n",
            ("diff", "--stat", "--", "src/zhar/cli/memory.py"): " src/zhar/cli/memory.py | 6 ++++--\n 1 file changed, 4 insertions(+), 2 deletions(-)\n",
            ("log", "--oneline", "-n", "5", "--", "src/zhar/cli/memory.py"): "abc1234 cli export\n",
        }

        def fake_run(args, cwd, capture_output, text, check):
            return SimpleNamespace(returncode=0, stdout=outputs.get(tuple(args[1:]), ""))

        monkeypatch.setattr(code_history_group.subprocess, "run", fake_run)

        store = MemStore(project)
        store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="cli export wiring",
            source="src/zhar/cli/memory.py::1::%ZHAR:ffff%",
            metadata={"significance": "feature"},
        ))

        result = runner.invoke(cli, [
            "--root", str(project), "export", "--group", "code_history", "--with-runtime-context",
        ])

        assert result.exit_code == 0
        assert "Runtime context" in result.output
        assert "git_companion" in result.output

    def test_export_omits_notes_by_default(self, project, runner):
        store = MemStore(project)
        base = make_node(
            group="project_dna",
            node_type="core_requirement",
            summary="Base requirement",
            content="## Why\n\nBecause.",
        )
        store.save(base)
        store.save(make_node(
            group="notes",
            node_type="note",
            summary="Imported note",
            content="Supplemental detail.",
            metadata={"target_ids": base.id, "agent": "copilot"},
        ))

        result = runner.invoke(cli, [
            "--root", str(project), "export",
        ])

        assert result.exit_code == 0, result.output
        assert "Base requirement" in result.output
        assert "Imported note" not in result.output

    def test_export_can_filter_by_tag(self, project, runner):
        runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Web requirement",
            "--tag", "project:web",
            "--content", "## Why\n\nWeb only.",
        ])
        runner.invoke(cli, [
            "--root", str(project), "add",
            "problem_tracking", "known_issue", "API issue",
            "--tag", "project:api",
            "--content", "## Details\n\nAPI only.",
        ])

        result = runner.invoke(cli, [
            "--root", str(project), "export", "--tag", "project:web",
        ])

        assert result.exit_code == 0, result.output
        assert "Web requirement" in result.output
        assert "API issue" not in result.output

    def test_export_does_not_pull_component_rel_nodes_into_unrelated_seed_groups(self, project, runner):
        store = MemStore(project)
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

        result = runner.invoke(cli, [
            "--root", str(project), "export", "--group", "project_dna",
            "--tag", "project:web", "--relation-depth", "1",
        ])

        assert result.exit_code == 0, result.output
        assert "Web requirement" in result.output
        assert "api -> db" not in result.output
        assert "web -> api" not in result.output

    def test_export_can_expand_across_built_in_links_group(self, project, runner):
        store = MemStore(project)
        source = store.save(make_node(
            group="code_history",
            node_type="file_change",
            summary="cli export wiring",
            tags=["project:web"],
        ))
        target = store.save(make_node(
            group="decision_trail",
            node_type="decision",
            summary="Linked decision context",
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

        result = runner.invoke(cli, [
            "--root", str(project), "export", "--group", "code_history",
            "--tag", "project:web", "--relation-depth", "1",
        ])

        assert result.exit_code == 0, result.output
        assert "cli export wiring" in result.output
        assert "Linked decision context" in result.output


class TestQueryNotes:
    def test_query_note_depth_zero_hides_attached_notes(self, project, runner):
        store = MemStore(project)
        base = make_node(
            group="decision_trail",
            node_type="decision",
            summary="Choose cached importer",
        )
        store.save(base)
        store.save(make_node(
            group="notes",
            node_type="note",
            summary="Migration rationale",
            content="Extra detail for import behavior.",
            metadata={"target_ids": base.id, "agent": "copilot"},
        ))

        result = runner.invoke(cli, [
            "--root", str(project), "query", "--q", "cached importer",
        ])

        assert result.exit_code == 0, result.output
        assert "Choose cached importer" in result.output
        assert "Migration rationale" not in result.output

    def test_query_note_depth_one_shows_attached_notes_under_match(self, project, runner):
        store = MemStore(project)
        base = make_node(
            group="decision_trail",
            node_type="decision",
            summary="Choose cached importer",
        )
        store.save(base)
        store.save(make_node(
            group="notes",
            node_type="note",
            summary="Migration rationale",
            content="Extra detail for import behavior.",
            metadata={"target_ids": base.id, "agent": "copilot"},
        ))

        result = runner.invoke(cli, [
            "--root", str(project), "query", "--q", "cached importer", "--note-depth", "1",
        ])

        assert result.exit_code == 0, result.output
        assert "Choose cached importer" in result.output
        assert "Migration rationale" in result.output
        assert "Extra detail for import behavior." in result.output
