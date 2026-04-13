"""Garbage collection — expire and archive stale nodes.

Two passes on every run:

1. **Expired** — nodes whose ``expires_at < utcnow()`` are deleted.
2. **Resolved → archived** — ``known_issue`` nodes with status ``resolved``
   are moved to ``archived`` so they stop appearing in active queries but
   stay in the historical record.

Both passes respect a ``dry_run`` flag that counts but does not mutate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from zhar.mem.node import patch_node
from zhar.mem.query import Query
from zhar.mem.store import MemStore
from zhar.utils.times import utcnow


@dataclass
class GcReport:
    """Summary of what a gc run did (or would do in dry_run mode)."""
    expired: int = 0
    archived: int = 0

    @property
    def total(self) -> int:
        return self.expired + self.archived


def run_gc(store: MemStore, *, dry_run: bool = False) -> GcReport:
    """Run garbage collection against *store*.

    Parameters
    ----------
    store:
        The MemStore to clean up.
    dry_run:
        When True, count affected nodes but do not write any changes.

    Returns
    -------
    GcReport
        Counts of nodes expired and archived.
    """
    report = GcReport()
    now = utcnow()

    for node in store.query(Query()):
        # ── pass 1: delete expired nodes ─────────────────────────────────────
        if node.expires_at is not None and node.expires_at <= now:
            if not dry_run:
                store.delete(node.id)
            report.expired += 1
            continue  # no need to check further passes for this node

        # ── pass 2: archive resolved known_issues ────────────────────────────
        if node.node_type == "known_issue" and node.status == "resolved":
            if not dry_run:
                store.save(patch_node(node, status="archived"))
            report.archived += 1

    return report
