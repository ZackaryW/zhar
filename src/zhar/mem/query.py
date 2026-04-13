"""Query interface — filter and search across the index and backends.

``Query`` is a plain dataclass of optional filter criteria.
``QueryEngine`` evaluates a Query against an index + backend pair.

All filters are AND-combined.  Multiple values within a single filter
(e.g. multiple groups) are OR-combined.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz

from zhar.mem.backends.base import Backend
from zhar.mem.index import MemIndex
from zhar.mem.node import Node, NodeRef


@dataclass
class Query:
    """Optional filter criteria.  None means "no constraint on this dimension"."""

    groups: list[str] | None = None
    node_types: list[str] | None = None
    statuses: list[str] | None = None
    tags: list[str] | None = None                # node must have ALL listed tags
    summary_contains: str | None = None          # case-insensitive substring / fuzzy
    limit: int | None = None


@dataclass(frozen=True)
class SummaryMatch:
    """A node + its fuzzy match score (0–1) for a summary_contains query."""
    node: Node
    score: float


class QueryEngine:
    """Evaluate Query objects against an in-memory index and a backend."""

    def __init__(self, index: MemIndex, backend: Backend) -> None:
        self._index = index
        self._backend = backend

    # ── public API ────────────────────────────────────────────────────────────

    def run(self, query: Query) -> list[Node]:
        """Return all nodes that satisfy *query* (no score information)."""
        refs = self._filter_refs(query)
        nodes = self._fetch(refs)
        if query.summary_contains:
            needle = query.summary_contains.lower()
            nodes = [n for n in nodes if needle in n.summary.lower()]
        if query.limit is not None:
            nodes = nodes[:query.limit]
        return nodes

    def run_with_scores(self, query: Query) -> list[SummaryMatch]:
        """Return SummaryMatch objects scored by summary similarity.

        Only meaningful when ``query.summary_contains`` is set.
        """
        nodes = self.run(query)
        if not query.summary_contains:
            return [SummaryMatch(node=n, score=1.0) for n in nodes]

        needle = query.summary_contains
        matches: list[SummaryMatch] = []
        for n in nodes:
            score = fuzz.partial_ratio(needle.lower(), n.summary.lower()) / 100.0
            matches.append(SummaryMatch(node=n, score=score))
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches

    # ── internal ──────────────────────────────────────────────────────────────

    def _filter_refs(self, query: Query) -> list[NodeRef]:
        """Apply index-level filters and return matching NodeRefs."""
        # Start from all refs; narrow down with each dimension
        candidate_ids: set[str] | None = None

        def narrow(ids: set[str]) -> None:
            nonlocal candidate_ids
            if candidate_ids is None:
                candidate_ids = ids
            else:
                candidate_ids &= ids

        if query.groups is not None:
            ids: set[str] = set()
            for g in query.groups:
                ids |= {r.id for r in self._index.by_group(g)}
            narrow(ids)

        if query.node_types is not None:
            ids = set()
            for t in query.node_types:
                ids |= {r.id for r in self._index.by_type(t)}
            narrow(ids)

        if query.statuses is not None:
            ids = set()
            for s in query.statuses:
                ids |= {r.id for r in self._index.by_status(s)}
            narrow(ids)

        if query.tags is not None:
            # Node must have ALL listed tags
            for tag in query.tags:
                tag_ids = {r.id for r in self._index.by_tag(tag)}
                narrow(tag_ids)

        if candidate_ids is None:
            # No index-level filters applied — return everything
            return self._index.all()

        return [self._index.get(i) for i in candidate_ids if self._index.get(i)]

    def _fetch(self, refs: list[NodeRef]) -> list[Node]:
        """Resolve NodeRefs to full Node objects via the backend."""
        nodes: list[Node] = []
        for ref in refs:
            node = self._backend.get(ref.id)
            if node is not None:
                nodes.append(node)
        return nodes
