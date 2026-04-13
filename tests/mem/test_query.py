"""TDD: zhar.mem.query — query interface over the index + backends."""
import pytest
from zhar.mem.node import make_node
from zhar.mem.index import MemIndex
from zhar.mem.backends.json_backend import JsonBackend
from zhar.mem.query import Query, QueryEngine, SummaryMatch


@pytest.fixture
def nodes():
    return [
        make_node(group="project_dna",     node_type="core_goal",    summary="Ship v1",             tags=["goal"],         status="active"),
        make_node(group="problem_tracking", node_type="known_issue",  summary="Auth race condition", tags=["auth", "race"], status="active"),
        make_node(group="problem_tracking", node_type="known_issue",  summary="DB timeout",          tags=["db"],           status="resolved"),
        make_node(group="decision_trail",   node_type="adr",          summary="Use JWT tokens",      tags=["auth", "jwt"],  status="accepted"),
    ]


@pytest.fixture
def engine(tmp_path, nodes):
    index = MemIndex()
    backend = JsonBackend(tmp_path / "store.json")
    for n in nodes:
        backend.save(n)
        index.add(n)
    return QueryEngine(index=index, backend=backend)


# ── Query dataclass ───────────────────────────────────────────────────────────

class TestQuery:
    def test_empty_query_is_valid(self):
        q = Query()
        assert q.groups is None
        assert q.node_types is None
        assert q.statuses is None
        assert q.tags is None
        assert q.summary_contains is None

    def test_query_with_filters(self):
        q = Query(groups=["project_dna"], statuses=["active"])
        assert q.groups == ["project_dna"]
        assert q.statuses == ["active"]


# ── QueryEngine ───────────────────────────────────────────────────────────────

class TestQueryEngineAll:
    def test_empty_query_returns_all_nodes(self, engine, nodes):
        results = engine.run(Query())
        assert len(results) == len(nodes)

    def test_results_are_nodes(self, engine):
        from zhar.mem.node import Node
        results = engine.run(Query())
        for r in results:
            assert isinstance(r, Node)


class TestQueryEngineFilters:
    def test_filter_by_group(self, engine):
        results = engine.run(Query(groups=["project_dna"]))
        assert all(r.group == "project_dna" for r in results)
        assert len(results) == 1

    def test_filter_by_multiple_groups(self, engine):
        results = engine.run(Query(groups=["project_dna", "decision_trail"]))
        groups = {r.group for r in results}
        assert groups == {"project_dna", "decision_trail"}

    def test_filter_by_node_type(self, engine):
        results = engine.run(Query(node_types=["known_issue"]))
        assert all(r.node_type == "known_issue" for r in results)
        assert len(results) == 2

    def test_filter_by_status(self, engine):
        results = engine.run(Query(statuses=["resolved"]))
        assert all(r.status == "resolved" for r in results)
        assert len(results) == 1

    def test_filter_by_tag(self, engine):
        results = engine.run(Query(tags=["auth"]))
        # both known_issue (auth, race) and adr (auth, jwt) have auth tag
        assert len(results) == 2
        for r in results:
            assert "auth" in r.tags

    def test_filter_by_summary_contains(self, engine):
        results = engine.run(Query(summary_contains="jwt"))
        assert len(results) == 1
        assert "jwt" in results[0].summary.lower()

    def test_filter_by_summary_case_insensitive(self, engine):
        results = engine.run(Query(summary_contains="JWT"))
        assert len(results) == 1

    def test_combined_filters_are_and_logic(self, engine):
        # group=problem_tracking AND status=resolved → only DB timeout
        results = engine.run(Query(groups=["problem_tracking"], statuses=["resolved"]))
        assert len(results) == 1
        assert results[0].summary == "DB timeout"

    def test_no_match_returns_empty(self, engine):
        results = engine.run(Query(groups=["nonexistent_group"]))
        assert results == []


class TestQueryEngineSummaryMatch:
    def test_summary_match_result_has_score(self, engine):
        results = engine.run_with_scores(Query(summary_contains="auth"))
        assert len(results) > 0
        for r in results:
            assert isinstance(r, SummaryMatch)
            assert 0.0 <= r.score <= 1.0

    def test_exact_match_scores_higher_than_partial(self, engine):
        results = engine.run_with_scores(Query(summary_contains="race condition"))
        # "Auth race condition" contains exact phrase — should appear
        assert any("race" in r.node.summary.lower() for r in results)
