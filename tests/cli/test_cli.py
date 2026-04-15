"""TDD: zhar CLI commands — init, add, mutation, query, and status."""
from types import SimpleNamespace
from pathlib import Path
import pytest
from click.testing import CliRunner

from zhar.cli import cli
from zhar.mem.node import make_node
from zhar.mem.store import MemStore


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
        assert "Agent Commands:" in result.output
        assert "Harness Commands:" in result.output
        assert "Stack Commands:" in result.output
        assert "  add     " in result.output
        assert "  add-note" in result.output
        assert "  set-status" in result.output
        assert "  remove    " in result.output
        assert "  prune     " in result.output
        assert "  facts  " in result.output
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
            ["--root", str(project), "note", nid, "--from-env", "ZHAR_NOTE_BODY"],
            env={"ZHAR_NOTE_BODY": "## Body\n\nFrom env."},
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
            ["--root", str(project), "note", nid, "--from-env", "ZHAR_NOTE_BODY"],
        )
        assert result.exit_code != 0
        assert "is not set" in result.output

    def test_note_rejects_content_and_env_var_together(self, project, runner):
        nid = self._add_adr(project, runner)
        result = runner.invoke(
            cli,
            ["--root", str(project), "note", nid, "literal", "--from-env", "ZHAR_NOTE_BODY"],
            env={"ZHAR_NOTE_BODY": "ignored"},
        )
        assert result.exit_code != 0
        assert "either CONTENT or --from-env" in result.output

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

    def test_show_can_expand_related_component_rel_nodes_within_tag_namespace(self, project, runner):
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
        assert "related nodes" in result.output.lower()
        assert "api -> db" in result.output
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

    def test_show_unknown_id_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, ["--root", str(project), "show", "zzzz"])
        assert result.exit_code != 0


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

    def test_export_can_expand_component_relations_within_tag_namespace(self, project, runner):
        store = MemStore(project)
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
            "--root", str(project), "export", "--group", "architecture_context",
            "--tag", "project:web", "--relation-depth", "1",
        ])

        assert result.exit_code == 0, result.output
        assert "web -> api" in result.output
        assert "api -> db" in result.output
        assert "api -> shared-db" not in result.output


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
