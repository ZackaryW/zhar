"""StackRegistry — per-project manifest of installed stack items.

Persisted at ``.zhar/cfg/stack.json``.  Tracks which agents, instructions,
skills, and hooks have been installed from bucket repos into this project.

Schema
------
.. code-block:: json

    {
      "<name>": {
        "repo": "org/repo",
        "branch": "main",
        "kind": "agent",
        "source_path": "agents/base.md",
        "installed_at": "2026-01-01T00:00:00"
      }
    }
"""
# %ZHAR:687d%
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import orjson

_VALID_KINDS = frozenset({"agent", "instruction", "skill", "hook"})


class StackRegistry:
    """Read/write the per-project stack manifest at *path*.

    Parameters
    ----------
    path:
        Absolute path to ``stack.json`` (e.g. ``.zhar/cfg/stack.json``).
        The file is created lazily on the first mutation.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    # ── public API ────────────────────────────────────────────────────────────

    def install(
        self,
        name: str,
        *,
        repo: str,
        branch: str,
        kind: str,
        source_path: str,
    ) -> dict[str, Any]:
        """Register *name* as installed and persist.

        Overwrites an existing entry with the same name.

        Parameters
        ----------
        name:        Logical identifier for this installed item.
        repo:        GitHub ``org/repo`` string.
        branch:      Branch in *repo*.
        kind:        One of ``agent | instruction | skill | hook``.
        source_path: Relative path within the repo to the source file/dir.

        Returns
        -------
        The newly written entry dict (without the ``name`` key).

        Raises
        ------
        ValueError
            If *kind* is not one of the valid values.
        """
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
        """Remove *name* from the registry.

        Returns ``True`` if it existed, ``False`` otherwise.
        """
        data = self._load()
        if name not in data:
            return False
        del data[name]
        self._save(data)
        return True

    def get(self, name: str) -> dict[str, Any] | None:
        """Return the entry for *name*, or ``None`` if not found."""
        return self._load().get(name)

    def list_items(self) -> list[dict[str, Any]]:
        """Return all installed items sorted by name, each with a ``name`` key."""
        data = self._load()
        items: list[dict[str, Any]] = []
        for name in sorted(data):
            item = dict(data[name])
            item["name"] = name
            items.append(item)
        return items

    def is_installed(self, name: str) -> bool:
        """Return ``True`` if *name* is in the registry."""
        return name in self._load()

    # ── internal ──────────────────────────────────────────────────────────────

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        raw = self._path.read_bytes()
        if not raw.strip():
            return {}
        return orjson.loads(raw)

    def _save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))
