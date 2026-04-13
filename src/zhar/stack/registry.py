"""StackRegistry — per-project manifest of installed stack items.

Persisted at ``.zhar/cfg/stack.json``. Tracks which agents, instructions,
skills, and hooks have been installed from bucket repos into this project.
"""
# %ZHAR:687d%
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson

_VALID_KINDS = frozenset({"agent", "instruction", "skill", "hook"})


class StackRegistry:
    """Read and write the per-project stack manifest at *path*."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def install(
        self,
        name: str,
        *,
        repo: str,
        branch: str,
        kind: str,
        source_path: str,
    ) -> dict[str, Any]:
        """Register *name* as installed and persist the registry."""
        if kind not in _VALID_KINDS:
            raise ValueError(
                f"Invalid kind {kind!r}. Must be one of: {sorted(_VALID_KINDS)}."
            )
        entry: dict[str, Any] = {
            "repo": repo,
            "branch": branch,
            "kind": kind,
            "source_path": source_path,
            "installed_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        data = self._load()
        data[name] = entry
        self._save(data)
        return entry

    def uninstall(self, name: str) -> bool:
        """Remove *name* from the registry."""
        data = self._load()
        if name not in data:
            return False
        del data[name]
        self._save(data)
        return True

    def get(self, name: str) -> dict[str, Any] | None:
        """Return the entry for *name*, or ``None`` if it is missing."""
        return self._load().get(name)

    def list_items(self) -> list[dict[str, Any]]:
        """Return all installed items sorted by name."""
        data = self._load()
        items: list[dict[str, Any]] = []
        for name in sorted(data):
            item = dict(data[name])
            item["name"] = name
            items.append(item)
        return items

    def is_installed(self, name: str) -> bool:
        """Return ``True`` when *name* exists in the registry."""
        return name in self._load()

    def _load(self) -> dict[str, Any]:
        """Load the registry from disk."""
        if not self._path.exists():
            return {}
        raw = self._path.read_bytes()
        if not raw.strip():
            return {}
        return orjson.loads(raw)

    def _save(self, data: dict[str, Any]) -> None:
        """Persist the registry to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))