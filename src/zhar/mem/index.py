"""MemIndex — in-memory cross-group thin index.

The index stores only NodeRef objects (lightweight pointers).  It is the
coordination layer between groups: it answers "which groups have a node with
tag X?" or "is there already a singleton of type Y in group Z?" without
touching any backend or deserialising full Node objects.

The index is rebuilt from backend data on startup; it is not persisted itself.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from zhar.mem.node import Node, NodeRef


class MemIndex:
    """In-memory index of NodeRef objects, keyed by multiple dimensions."""

    def __init__(self) -> None:
        self._by_id: dict[str, NodeRef] = {}
        self._by_group: dict[str, list[str]] = defaultdict(list)    # group → [ids]
        self._by_type: dict[str, list[str]] = defaultdict(list)     # type  → [ids]
        self._by_status: dict[str, list[str]] = defaultdict(list)   # status → [ids]
        self._by_tag: dict[str, list[str]] = defaultdict(list)      # tag   → [ids]

    # ── mutating ──────────────────────────────────────────────────────────────

    def add(self, node: Node) -> NodeRef:
        """Index *node* and return its NodeRef.

        If a node with the same ID already exists it is replaced (all old index
        entries for that ID are cleaned up first).
        """
        if node.id in self._by_id:
            self._remove_refs(node.id)

        ref = NodeRef.from_node(node)
        self._by_id[node.id] = ref
        self._by_group[node.group].append(node.id)
        self._by_type[node.node_type].append(node.id)
        self._by_status[node.status].append(node.id)
        for tag in node.tags:
            self._by_tag[tag].append(node.id)
        return ref

    def remove(self, node_id: str) -> bool:
        """Remove *node_id* from the index.  Returns True if it existed."""
        if node_id not in self._by_id:
            return False
        self._remove_refs(node_id)
        del self._by_id[node_id]
        return True

    # ── queries ───────────────────────────────────────────────────────────────

    def get(self, node_id: str) -> NodeRef | None:
        return self._by_id.get(node_id)

    def all(self) -> list[NodeRef]:
        return list(self._by_id.values())

    def count(self) -> int:
        return len(self._by_id)

    def by_group(self, group: str) -> list[NodeRef]:
        return self._resolve(self._by_group.get(group, []))

    def by_type(self, node_type: str) -> list[NodeRef]:
        return self._resolve(self._by_type.get(node_type, []))

    def by_status(self, status: str) -> list[NodeRef]:
        return self._resolve(self._by_status.get(status, []))

    def by_tag(self, tag: str) -> list[NodeRef]:
        return self._resolve(self._by_tag.get(tag, []))

    def singleton(self, group: str, node_type: str) -> NodeRef | None:
        """Return the active singleton NodeRef for *group*/*node_type*, or None."""
        candidates = [
            ref for ref in self.by_group(group)
            if ref.node_type == node_type and ref.status == "active"
        ]
        return candidates[0] if candidates else None

    # ── internal ──────────────────────────────────────────────────────────────

    def _resolve(self, ids: Iterable[str]) -> list[NodeRef]:
        """Map IDs to NodeRefs, skipping any that have been removed."""
        return [self._by_id[i] for i in ids if i in self._by_id]

    def _remove_refs(self, node_id: str) -> None:
        """Remove *node_id* from all secondary index lists (not _by_id)."""
        old = self._by_id[node_id]
        _drop(self._by_group[old.group], node_id)
        _drop(self._by_type[old.node_type], node_id)
        _drop(self._by_status[old.status], node_id)
        # tags are on the Node, not NodeRef; we can't recover them here
        # clean up by scanning tag index — acceptable for small graphs
        for ids in self._by_tag.values():
            _drop(ids, node_id)


def _drop(lst: list[str], value: str) -> None:
    try:
        lst.remove(value)
    except ValueError:
        pass
