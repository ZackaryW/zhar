"""MemStore — central coordinator for zhar memory.

Responsibilities
----------------
- Resolve the on-disk layout: one JSON file per group under ``store_dir/``
- Load all group definitions (built-ins + user-defined via cfg_dir)
- Build and maintain a live MemIndex rebuilt from backends on startup
- Enforce singleton and memory_backed constraints before writing
- Provide a group-unaware save / get / delete / query surface
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from zhar.mem.backends.json_backend import JsonBackend
from zhar.mem.group import GroupDef
from zhar.mem.ids import make_id_unique, new_id
from zhar.mem.index import MemIndex
from zhar.mem.loader import load_all_groups
from zhar.mem.node import Node, patch_node
from zhar.mem.query import Query, QueryEngine


# Default sub-directory name inside the project root
_MEM_SUBDIR = "mem"
_CFG_SUBDIR = "cfg"


class MemStore:
    # %ZHAR:4f8b%
    """Unified memory store for all groups.

    Parameters
    ----------
    root:
        The ``.zhar/`` directory (or any directory that acts as the store root).
        ``store_dir`` will be ``root/mem/`` and ``cfg_dir`` will be
        ``root/cfg/``.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self.store_dir: Path = root / _MEM_SUBDIR
        self._cfg_dir: Path = root / _CFG_SUBDIR

        # Ensure directories exist
        self.store_dir.mkdir(parents=True, exist_ok=True)

        # Load group definitions
        self.groups: dict[str, GroupDef] = load_all_groups(self._cfg_dir)

        # One JsonBackend per group
        self._backends: dict[str, JsonBackend] = {
            name: JsonBackend(self.store_dir / f"{name}.json")
            for name in self.groups
        }

        # In-memory index — rebuilt from backends
        self.index: MemIndex = MemIndex()
        self._rebuild_index()

    # ── public API ────────────────────────────────────────────────────────────

    def save(self, node: Node) -> Node:
        """Persist *node* and update the index.

        Raises
        ------
        ValueError
            If a different node of the same singleton type already exists,
            or if *node* carries ``content`` on a non-memory-backed type.
        KeyError
            If *node.group* is not a known group.
        """
        node = self._normalize_for_persistence(node)
        self._validate(node)
        backend = self._backend_for(node.group)
        backend.save(node)
        self.index.add(node)
        return node

    def get(self, node_id: str) -> Node | None:
        """Return the full Node for *node_id*, or None if not found."""
        # Scan all backends — we don't know which group it belongs to from ID alone
        ref = self.index.get(node_id)
        if ref is None:
            return None
        return self._backend_for(ref.group).get(node_id)

    def delete(self, node_id: str) -> bool:
        """Remove *node_id* from its backend and the index.

        Returns True if it existed, False otherwise.
        """
        ref = self.index.get(node_id)
        if ref is None:
            return False
        self._backend_for(ref.group).delete(node_id)
        self.index.remove(node_id)
        return True

    def query(self, q: Query) -> list[Node]:
        """Run *q* against the store and return matching Nodes."""
        return self._engine().run(q)

    def query_with_scores(self, q: Query):  # -> list[SummaryMatch]
        """Run *q* with fuzzy scoring against the store."""
        return self._engine().run_with_scores(q)

    def stats(self) -> dict[str, dict[str, Any]]:
        """Return per-group statistics: total count, breakdown by node_type."""
        result: dict[str, dict[str, Any]] = {}
        for name, group_def in self.groups.items():
            refs = self.index.by_group(name)
            by_type: dict[str, int] = {nt.name: 0 for nt in group_def.node_types}
            for ref in refs:
                if ref.node_type in by_type:
                    by_type[ref.node_type] += 1
            result[name] = {"total": len(refs), "by_type": by_type}
        return result

    def allocate_id(self, preferred: str | None = None, *, length: int = 5) -> str:
        """Return a store-aware unique node ID.

        ``preferred`` is preserved when possible, which allows migrations to keep
        legacy IDs if they do not collide with existing records.
        """
        taken = {ref.id for ref in self.index.all()}
        if preferred is not None:
            return make_id_unique(preferred, taken, length=len(preferred))
        return make_id_unique(new_id(length=length, taken=taken), taken, length=length)

    def attached_notes(self, node_id: str) -> list[Node]:
        """Return note nodes that attach to ``node_id``."""
        notes_group = self.groups.get("notes")
        if notes_group is None:
            return []

        attached: list[Node] = []
        for node in self.query(Query(groups=["notes"])):
            target_ids = node.metadata.get("target_ids", "")
            targets = [part.strip() for part in str(target_ids).split(",") if part.strip()]
            if node_id in targets:
                attached.append(node)
        return attached

    @property
    def root(self) -> Path:
        """Return the ``.zhar`` root directory for this store."""
        return self._root

    @property
    def project_root(self) -> Path:
        """Return the project root that contains this store."""
        return self._root.parent

    # ── internal ──────────────────────────────────────────────────────────────

    def _backend_for(self, group: str) -> JsonBackend:
        try:
            return self._backends[group]
        except KeyError:
            raise KeyError(
                f"Unknown group '{group}'. Known groups: {list(self.groups)}"
            )

    def _normalize_for_persistence(self, node: Node) -> Node:
        """Return *node* normalized to current storage semantics.

        ``code_history/file_change`` uses ``source`` as the authoritative file
        locator once a marker exists. In that state, ``metadata.path`` is stale
        duplicate data and is removed before writing.
        """
        if node.group != "code_history" or node.node_type != "file_change":
            return node
        if node.source is None:
            return node
        if "path" not in node.metadata:
            return node
        return patch_node(node, metadata={"path": None})

    def _validate(self, node: Node) -> None:
        """Raise ValueError for constraint violations before writing."""
        group_def = self.groups.get(node.group)
        if group_def is None:
            raise KeyError(
                f"Unknown group '{node.group}'. Known groups: {list(self.groups)}"
            )

        try:
            type_def = group_def.get_type(node.node_type)
        except KeyError:
            raise KeyError(
                f"Unknown node type '{node.node_type}' in group '{node.group}'."
            )

        if node.group == "notes" and node.node_type == "note":
            self._validate_note_targets(node)

        # content must be None for non-memory-backed types
        if node.content is not None and not type_def.memory_backed:
            raise ValueError(
                f"Node type '{node.node_type}' in group '{node.group}' is not "
                f"memory_backed — 'content' must be None. "
                f"Set memory_backed=True on the NodeTypeDef to allow content."
            )

        # singleton: reject a *different* active node of the same type
        if type_def.singleton:
            existing = self.index.singleton(node.group, node.node_type)
            if existing is not None and existing.id != node.id:
                raise ValueError(
                    f"Node type '{node.node_type}' in group '{node.group}' is a "
                    f"singleton — an active node already exists (id={existing.id}). "
                    f"Archive or delete it before adding a new one."
                )

    def _validate_note_targets(self, node: Node) -> None:
        """Validate that note nodes attach to at least one non-note node."""
        target_ids = [part.strip() for part in str(node.metadata.get("target_ids", "")).split(",") if part.strip()]
        if not target_ids:
            raise ValueError("Note nodes must declare at least one target via metadata.target_ids.")

        for target_id in target_ids:
            target_ref = self.index.get(target_id)
            if target_ref is None:
                raise ValueError(f"Note target '{target_id}' does not exist.")
            if target_ref.group == "notes":
                raise ValueError("Note nodes cannot target other note nodes.")

    def _rebuild_index(self) -> None:
        """Populate the index from all backends (called once on startup)."""
        for name, backend in self._backends.items():
            for node in backend.list_all():
                self.index.add(node)

    def _engine(self) -> QueryEngine:
        """Build a QueryEngine that fans queries across all backends.

        We use a single composite backend that routes get() calls via the
        index → correct per-group backend.
        """
        return QueryEngine(index=self.index, backend=_FanoutBackend(self))


class _FanoutBackend:
    """Thin adapter so QueryEngine can call .get(id) without knowing the group."""

    def __init__(self, store: MemStore) -> None:
        self._store = store

    def get(self, node_id: str) -> Node | None:
        return self._store.get(node_id)

    # The remaining Backend protocol methods are not needed by QueryEngine
    # but we provide stubs so isinstance(b, Backend) works if checked.
    def save(self, node: Node) -> None:  # pragma: no cover
        self._store.save(node)

    def delete(self, node_id: str) -> bool:  # pragma: no cover
        return self._store.delete(node_id)

    def list_all(self) -> list[Node]:  # pragma: no cover
        return self._store.query(Query())

    def exists(self, node_id: str) -> bool:  # pragma: no cover
        return self._store.index.get(node_id) is not None
