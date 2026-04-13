"""TDD: zhar CLI commands — init, add, note, show, query, status."""
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


# ── add ───────────────────────────────────────────────────────────────────────

class TestAdd:
    def test_add_prints_node_id(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Support pluggable backends",
        ])
        assert result.exit_code == 0, result.output
        # output should contain the new node ID (4 hex chars)
        import re
        assert re.search(r"Added [0-9a-f]{4}", result.output)

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
        return re.search(r"Added ([0-9a-f]{4})", result.output).group(1)

    def test_note_sets_content(self, project, runner):
        nid = self._add_adr(project, runner)
        result = runner.invoke(cli, [
            "--root", str(project), "note", nid, "## Body\n\nDetails.",
        ])
        assert result.exit_code == 0, result.output

    def test_note_on_non_backed_type_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_goal", "A goal",
        ])
        import re
        nid = re.search(r"Added ([0-9a-f]{4})", result.output).group(1)
        result2 = runner.invoke(cli, [
            "--root", str(project), "note", nid, "Some content",
        ])
        assert result2.exit_code != 0

    def test_note_unknown_id_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, [
            "--root", str(project), "note", "zzzz", "content",
        ])
        assert result.exit_code != 0


# ── show ──────────────────────────────────────────────────────────────────────

class TestShow:
    def test_show_displays_summary(self, project, runner):
        add = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "Must support TDD",
        ])
        import re
        nid = re.search(r"Added ([0-9a-f]{4})", add.output).group(1)
        result = runner.invoke(cli, ["--root", str(project), "show", nid])
        assert result.exit_code == 0, result.output
        assert "Must support TDD" in result.output

    def test_show_displays_group_and_type(self, project, runner):
        add = runner.invoke(cli, [
            "--root", str(project), "add",
            "project_dna", "core_requirement", "A requirement",
        ])
        import re
        nid = re.search(r"Added ([0-9a-f]{4})", add.output).group(1)
        result = runner.invoke(cli, ["--root", str(project), "show", nid])
        assert "project_dna" in result.output
        assert "core_requirement" in result.output

    def test_show_unknown_id_exits_nonzero(self, project, runner):
        result = runner.invoke(cli, ["--root", str(project), "show", "zzzz"])
        assert result.exit_code != 0


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
