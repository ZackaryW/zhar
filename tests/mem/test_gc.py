"""TDD: zhar.mem.gc — garbage collection."""
from datetime import timedelta
from pathlib import Path
import pytest
from zhar.mem.gc import run_gc, GcReport
from zhar.mem.store import MemStore
from zhar.mem.node import make_node
from zhar.utils.times import utcnow


@pytest.fixture
def store(tmp_path) -> MemStore:
    return MemStore(tmp_path / ".zhar")


# ── expired nodes ─────────────────────────────────────────────────────────────

class TestExpired:
    def test_removes_expired_node(self, store):
        past = utcnow() - timedelta(hours=1)
        n = make_node(group="project_dna", node_type="core_requirement",
                      summary="Stale req", expires_at=past)
        store.save(n)
        report = run_gc(store)
        assert store.get(n.id) is None
        assert report.expired == 1

    def test_keeps_non_expired_node(self, store):
        future = utcnow() + timedelta(hours=1)
        n = make_node(group="project_dna", node_type="core_requirement",
                      summary="Still valid", expires_at=future)
        store.save(n)
        report = run_gc(store)
        assert store.get(n.id) is not None
        assert report.expired == 0

    def test_keeps_node_with_no_expiry(self, store):
        n = make_node(group="project_dna", node_type="core_requirement",
                      summary="No expiry")
        store.save(n)
        run_gc(store)
        assert store.get(n.id) is not None

    def test_dry_run_does_not_delete(self, store):
        past = utcnow() - timedelta(hours=1)
        n = make_node(group="project_dna", node_type="core_requirement",
                      summary="Expired but dry", expires_at=past)
        store.save(n)
        report = run_gc(store, dry_run=True)
        assert store.get(n.id) is not None   # not deleted
        assert report.expired == 1            # but counted


# ── resolved issues auto-archived ────────────────────────────────────────────

class TestResolvedIssues:
    def test_resolved_known_issue_archived(self, store):
        n = make_node(group="problem_tracking", node_type="known_issue",
                      summary="Fixed bug", status="resolved")
        store.save(n)
        report = run_gc(store)
        updated = store.get(n.id)
        assert updated.status == "archived"
        assert report.archived == 1

    def test_active_known_issue_untouched(self, store):
        n = make_node(group="problem_tracking", node_type="known_issue",
                      summary="Active bug", status="active")
        store.save(n)
        run_gc(store)
        assert store.get(n.id).status == "active"

    def test_dry_run_does_not_archive(self, store):
        n = make_node(group="problem_tracking", node_type="known_issue",
                      summary="Fixed", status="resolved")
        store.save(n)
        report = run_gc(store, dry_run=True)
        assert store.get(n.id).status == "resolved"
        assert report.archived == 1


# ── GcReport ─────────────────────────────────────────────────────────────────

class TestGcReport:
    def test_empty_store_all_zeros(self, store):
        report = run_gc(store)
        assert report.expired == 0
        assert report.archived == 0

    def test_report_is_additive(self, store):
        past = utcnow() - timedelta(hours=1)
        n1 = make_node(group="project_dna", node_type="core_requirement",
                       summary="Expired", expires_at=past)
        n2 = make_node(group="problem_tracking", node_type="known_issue",
                       summary="Resolved", status="resolved")
        store.save(n1)
        store.save(n2)
        report = run_gc(store)
        assert report.expired == 1
        assert report.archived == 1
        assert report.total == 2
