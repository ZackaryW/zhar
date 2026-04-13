"""Backend Protocol — the interface all storage backends must satisfy."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from zhar.mem.node import Node


@runtime_checkable
class Backend(Protocol):
    """Minimal storage contract for a group backend.

    All methods operate on a single group's namespace.  The backend is
    responsible only for persistence; validation happens in the group layer.
    """

    def save(self, node: Node) -> None:
        """Persist *node*, overwriting any existing entry with the same ID."""
        ...

    def get(self, node_id: str) -> Node | None:
        """Return the Node for *node_id*, or None if not found."""
        ...

    def delete(self, node_id: str) -> bool:
        """Remove *node_id*.  Return True if it existed, False otherwise."""
        ...

    def list_all(self) -> list[Node]:
        """Return all nodes in this backend (no ordering guarantee)."""
        ...

    def exists(self, node_id: str) -> bool:
        """Return True if *node_id* is stored."""
        ...
