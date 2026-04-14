"""Integration tests against the checked-in zhar memory fixture."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from zhar.cli import cli
from zhar.mem.export import export_text
from zhar.mem.query import Query
from zhar.mem.store import MemStore
from zhar.mem.verify import run_verify

_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "test_src"
_EXPECTED_TOTALS = {
    "project_dna": 7,
    "problem_tracking": 1,
    "decision_trail": 16,
    "code_history": 18,
    "notes": 0,
}
_EXPECTED_MISSING_CONTENT_IDS = {
    "f6ce",
    "5518",
    "ed31",
    "07fb",
    "c30a",
    "b95f",
    "992f",
    "19f1",
}


def _fixture_store() -> MemStore:
    """Return a MemStore opened against the checked-in integration fixture."""
    return MemStore(_FIXTURE_ROOT)


def test_fixture_store_loads_expected_snapshot() -> None:
    """The copied fixture should load with the expected group counts and nodes."""
    store = _fixture_store()

    stats = store.stats()

    assert {group: data["total"] for group, data in stats.items()} == _EXPECTED_TOTALS

    core_goal = store.get("ffad")
    assert core_goal is not None
    assert core_goal.summary.startswith("Build zhar")

    adr = store.get("c4b6")
    assert adr is not None
    assert "group-clustered JSON files" in adr.summary
    assert adr.content is not None
    assert "## Decision" in adr.content


def test_fixture_query_returns_expected_live_nodes() -> None:
    """Querying the copied fixture should return known nodes from multiple groups."""
    store = _fixture_store()

    stack_nodes = store.query(Query(summary_contains="stack template", limit=10))
    stack_ids = {node.id for node in stack_nodes}

    assert {"f3a6", "5969", "1782", "5dc4"}.issubset(stack_ids)

    file_changes = store.query(Query(groups=["code_history"], summary_contains="installer"))
    assert [node.id for node in file_changes] == ["530d"]
    assert file_changes[0].source == "src/zhar/agents/installer.py::25::%ZHAR:530d%"


def test_cli_reads_the_copied_fixture_snapshot() -> None:
    """The CLI should report and display data from the copied fixture without mutation."""
    runner = CliRunner()

    status_result = runner.invoke(cli, ["--root", str(_FIXTURE_ROOT), "status"])
    show_result = runner.invoke(cli, ["--root", str(_FIXTURE_ROOT), "show", "c4b6"])
    query_result = runner.invoke(
        cli,
        ["--root", str(_FIXTURE_ROOT), "query", "--group", "decision_trail", "--q", "group-clustered"],
    )

    assert status_result.exit_code == 0, status_result.output
    assert "Total nodes: 42" in status_result.output
    assert "project_dna  (7)" in status_result.output
    assert "code_history  (18)" in status_result.output

    assert show_result.exit_code == 0, show_result.output
    assert "Use group-clustered JSON files instead of a flat zmem-style graph" in show_result.output
    assert "## Status" in show_result.output

    assert query_result.exit_code == 0, query_result.output
    assert "c4b6" in query_result.output


def test_export_and_verify_match_the_copied_fixture() -> None:
    """Export and verify should reflect the copied fixture's current behavior."""
    store = _fixture_store()

    exported = export_text(store, project_root=_FIXTURE_ROOT.parent)
    issues = run_verify(store, project_root=_FIXTURE_ROOT.parent)

    assert "Build zhar: a group-clustered agent memory harness" in exported
    assert "source=src/zhar/agents/installer.py::25::%ZHAR:530d%" in exported

    issue_codes = {issue.code for issue in issues}
    missing_content_ids = {
        issue.message.split("[", 1)[1].split("]", 1)[0]
        for issue in issues
        if issue.code == "MISSING_CONTENT"
    }

    assert issue_codes == {"MISSING_CONTENT"}
    assert missing_content_ids == _EXPECTED_MISSING_CONTENT_IDS