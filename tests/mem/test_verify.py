"""TDD: zhar.mem.verify — completeness checks."""
from pathlib import Path
import pytest
from zhar.mem.verify import run_verify, VerifyIssue, Severity
from zhar.mem.store import MemStore
from zhar.mem.node import make_node


@pytest.fixture
def store(tmp_path) -> MemStore:
    return MemStore(tmp_path / ".zhar")


# ── VerifyIssue ───────────────────────────────────────────────────────────────

class TestVerifyIssue:
    def test_fields(self):
        issue = VerifyIssue(severity=Severity.WARN, code="MISSING_SINGLETON",
                            message="No core_goal set")
        assert issue.severity == Severity.WARN
        assert issue.code == "MISSING_SINGLETON"
        assert "core_goal" in issue.message


# ── missing singletons ────────────────────────────────────────────────────────

class TestMissingSingleton:
    def test_warns_when_core_goal_missing(self, store):
        issues = run_verify(store)
        codes = [i.code for i in issues]
        assert "MISSING_SINGLETON" in codes

    def test_no_warning_when_core_goal_present(self, store):
        store.save(make_node(group="project_dna", node_type="core_goal",
                             summary="Build it"))
        issues = run_verify(store)
        singleton_issues = [i for i in issues if i.code == "MISSING_SINGLETON"]
        assert not singleton_issues


# ── memory-backed nodes without content ──────────────────────────────────────

class TestMissingContent:
    def test_warns_when_backed_node_has_no_content(self, store):
        store.save(make_node(group="decision_trail", node_type="adr",
                             summary="Some ADR", content=None))
        issues = run_verify(store)
        codes = [i.code for i in issues]
        assert "MISSING_CONTENT" in codes

    def test_no_warning_when_backed_node_has_content(self, store):
        store.save(make_node(group="decision_trail", node_type="adr",
                             summary="Some ADR", content="## Details\nHere."))
        issues = run_verify(store)
        content_issues = [i for i in issues if i.code == "MISSING_CONTENT"]
        assert not content_issues

    def test_non_backed_node_without_content_not_flagged(self, store):
        store.save(make_node(group="project_dna", node_type="core_goal",
                             summary="Goal"))
        issues = run_verify(store)
        # core_goal is not memory_backed — no MISSING_CONTENT warning
        content_issues = [i for i in issues
                          if i.code == "MISSING_CONTENT" and "core_goal" in i.message]
        assert not content_issues


# ── broken source references ──────────────────────────────────────────────────

class TestBrokenSource:
    def test_warns_when_source_file_missing(self, store, tmp_path):
        n = make_node(group="project_dna", node_type="core_requirement",
                      summary="Req", source="src/ghost.py::10::%ZHAR:a1b2%")
        store.save(n)
        issues = run_verify(store, project_root=tmp_path)
        codes = [i.code for i in issues]
        assert "BROKEN_SOURCE" in codes

    def test_no_warning_when_source_file_exists(self, store, tmp_path):
        src = tmp_path / "src" / "real.py"
        src.parent.mkdir(parents=True)
        src.write_text("# code\n")
        n = make_node(group="project_dna", node_type="core_requirement",
                      summary="Req", source=f"src/real.py::1::%ZHAR:a1b2%")
        store.save(n)
        issues = run_verify(store, project_root=tmp_path)
        broken = [i for i in issues if i.code == "BROKEN_SOURCE"]
        assert not broken

    def test_no_warning_when_no_source_set(self, store, tmp_path):
        n = make_node(group="project_dna", node_type="core_requirement",
                      summary="No source")
        store.save(n)
        issues = run_verify(store, project_root=tmp_path)
        broken = [i for i in issues if i.code == "BROKEN_SOURCE"]
        assert not broken


# ── overall ───────────────────────────────────────────────────────────────────

class TestRunVerify:
    def test_returns_list(self, store):
        assert isinstance(run_verify(store), list)

    def test_fully_healthy_store_minimal_issues(self, store):
        store.save(make_node(group="project_dna", node_type="core_goal",
                             summary="Build it"))
        issues = run_verify(store)
        # No MISSING_SINGLETON, no MISSING_CONTENT, no BROKEN_SOURCE
        critical_codes = {"MISSING_SINGLETON", "MISSING_CONTENT", "BROKEN_SOURCE"}
        found = {i.code for i in issues} & critical_codes
        assert not found
