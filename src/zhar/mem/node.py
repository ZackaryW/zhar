"""Core Node dataclass — the atomic unit of zhar memory.

Nodes are frozen (immutable structural fields); mutable state is changed by
producing a new Node via ``patch_node``.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from zhar.mem.ids import new_id
from zhar.utils.times import utcnow

# Fields that must never change after creation.
IMMUTABLE_FIELDS: frozenset[str] = frozenset({"id", "group", "node_type", "created_at"})


@dataclass(frozen=True)
class Node:
    """Immutable node record.

    ``metadata`` holds group/type-defined fields (light semantic).
    ``custom``   holds free-form agent/user annotations — never validated.
    """

    id: str
    group: str
    node_type: str
    summary: str
    status: str
    # Internal tuple for immutability; exposed as list via property
    _tags: tuple[str, ...]              = field(repr=False)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    source: str | None
    # %ZHAR:c3b0%
    # Full markdown body for memory-backed node types (None for graph-only nodes)
    content: str | None
    # stored as tuples internally but exposed as dicts/lists via properties
    _metadata: tuple[tuple[str, Any], ...]  = field(repr=False)
    _custom: tuple[tuple[str, Any], ...]    = field(repr=False)

    # ── public views (always return mutable copies) ───────────────────────────

    @property
    def tags(self) -> list[str]:
        return list(self._tags)

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    @property
    def custom(self) -> dict[str, Any]:
        return dict(self._custom)


@dataclass(frozen=True)
class NodeRef:
    """Lightweight pointer to a node — used in query results and index entries."""

    id: str
    group: str
    node_type: str
    status: str
    summary: str

    @classmethod
    def from_node(cls, node: Node) -> "NodeRef":
        return cls(
            id=node.id,
            group=node.group,
            node_type=node.node_type,
            status=node.status,
            summary=node.summary,
        )


# ── factory ───────────────────────────────────────────────────────────────────

def make_node(
    *,
    group: str,
    node_type: str,
    summary: str,
    status: str = "active",
    tags: list[str] | None = None,
    source: str | None = None,
    content: str | None = None,
    expires_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    custom: dict[str, Any] | None = None,
    node_id: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> Node:
    """Construct a new Node with a fresh ID and timestamps.

    ``created_at`` and ``updated_at`` are accepted so that backends can restore
    persisted nodes without altering their timestamps.
    ``content`` carries the full markdown body for memory-backed node types;
    it is ``None`` for graph-only nodes.
    """
    now = utcnow()
    return Node(
        id=node_id or new_id(),
        group=group,
        node_type=node_type,
        summary=summary,
        status=status,
        _tags=tuple(tags or []),
        created_at=created_at or now,
        updated_at=updated_at or now,
        expires_at=expires_at,
        source=source,
        content=content,
        _metadata=tuple((metadata or {}).items()),
        _custom=tuple((custom or {}).items()),
    )


# ── patch ─────────────────────────────────────────────────────────────────────

def patch_node(node: Node, **kwargs: Any) -> Node:
    """Return a new Node with the given mutable fields updated.

    - ``metadata`` and ``custom`` are *shallow-merged* (not replaced).
    - Setting a custom/metadata value to ``None`` removes the key.
    - Attempting to change an IMMUTABLE_FIELD raises ``ValueError``.
    - ``updated_at`` is always refreshed.
    """
    illegal = set(kwargs) & IMMUTABLE_FIELDS
    if illegal:
        raise ValueError(f"Cannot patch immutable fields: {sorted(illegal)}")

    # Merge metadata
    if "metadata" in kwargs:
        merged_meta = dict(node._metadata)
        for k, v in kwargs.pop("metadata").items():
            if v is None:
                merged_meta.pop(k, None)
            else:
                merged_meta[k] = v
        kwargs["_metadata"] = tuple(merged_meta.items())

    # Merge custom
    if "custom" in kwargs:
        merged_custom = dict(node._custom)
        for k, v in kwargs.pop("custom").items():
            if v is None:
                merged_custom.pop(k, None)
            else:
                merged_custom[k] = v
        kwargs["_custom"] = tuple(merged_custom.items())

    # Coerce tags to internal _tags tuple if supplied
    if "tags" in kwargs:
        kwargs["_tags"] = tuple(kwargs.pop("tags"))

    kwargs["updated_at"] = utcnow()
    return replace(node, **kwargs)
