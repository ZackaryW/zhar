"""JSON file backend — default storage for a single group.

File layout
-----------
One JSON object per group, stored at the path provided on construction::

    {
        "<node-id>": { ...serialised Node fields... },
        ...
    }

The file is read via ``MtimeFileCache`` so repeated reads within one process
pay no disk I/O cost as long as the file mtime does not change.  The cache
entry is invalidated on every write so the next read always reflects what is
on disk.

orjson is a hard dependency — it is used for both reads and writes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import orjson

from zhar.mem.node import Node, make_node
from zhar.utils.cache import MtimeFileCache
from zhar.utils.times import format_dt, parse_dt

# Module-level shared cache — shared across all JsonBackend instances so that
# different backends pointing at the same file benefit from the same hot entry.
_FILE_CACHE = MtimeFileCache()


class JsonBackend:
    # %ZHAR:4e64%
    """Persist nodes for one group as an orjson-serialised JSON file."""

    def __init__(self, path: Path, *, cache: MtimeFileCache | None = None) -> None:
        self._path = path
        self._cache = cache if cache is not None else _FILE_CACHE

    # ── Backend protocol ─────────────────────────────────────────────────────

    def save(self, node: Node) -> None:
        data = self._read()
        data[node.id] = _node_to_dict(node)
        self._write(data)

    def get(self, node_id: str) -> Node | None:
        raw = self._read().get(node_id)
        return _dict_to_node(raw) if raw is not None else None

    def delete(self, node_id: str) -> bool:
        data = self._read()
        if node_id not in data:
            return False
        del data[node_id]
        self._write(data)
        return True

    def list_all(self) -> list[Node]:
        return [_dict_to_node(v) for v in self._read().values()]

    def exists(self, node_id: str) -> bool:
        return node_id in self._read()

    # ── internal I/O ─────────────────────────────────────────────────────────

    def _read(self) -> dict[str, Any]:
        raw = self._cache.read_bytes(self._path)
        if not raw:
            return {}
        return orjson.loads(raw)

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        serialised = orjson.dumps(data, option=orjson.OPT_INDENT_2)
        self._path.write_bytes(serialised)
        # Invalidate so next _read reflects the file we just wrote.
        self._cache.invalidate(self._path)


# ── serialisation helpers ─────────────────────────────────────────────────────

def _node_to_dict(node: Node) -> dict[str, Any]:
    return {
        "id": node.id,
        "group": node.group,
        "node_type": node.node_type,
        "summary": node.summary,
        "status": node.status,
        "tags": list(node.tags),
        "source": node.source,
        "content": node.content,
        "created_at": format_dt(node.created_at),
        "updated_at": format_dt(node.updated_at),
        "expires_at": format_dt(node.expires_at) if node.expires_at else None,
        "metadata": node.metadata,
        "custom": node.custom,
    }


def _dict_to_node(d: dict[str, Any]) -> Node:
    return make_node(
        node_id=d["id"],
        group=d["group"],
        node_type=d["node_type"],
        summary=d["summary"],
        status=d.get("status", "active"),
        tags=d.get("tags", []),
        source=d.get("source"),
        content=d.get("content"),
        created_at=parse_dt(d["created_at"]) if d.get("created_at") else None,
        updated_at=parse_dt(d["updated_at"]) if d.get("updated_at") else None,
        expires_at=parse_dt(d["expires_at"]) if d.get("expires_at") else None,
        metadata=d.get("metadata", {}),
        custom=d.get("custom", {}),
    )
