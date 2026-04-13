"""Facts — project and global string key-value stores for zhar.

Project facts are persisted as ``.zhar/facts.json`` inside a repository.
Global facts are persisted as ``Path.home() / '.zhar' / 'facts.json'``.
All keys and values are strings. Facts have no dependency on the memory
system; they are a standalone configuration primitive that other subsystems
(harness, export, stack templates) can read.

Example ``facts.json``::

    {
      "is_python_project": "uv",
      "test_runner": "pytest",
      "primary_language": "python",
      "has_cli": "true"
    }
"""
from __future__ import annotations

from pathlib import Path

import orjson


def project_facts_path(zhar_root: Path) -> Path:
    """Return the project-local facts file path for *zhar_root*."""
    return zhar_root / "facts.json"


def global_facts_path(home: Path | None = None) -> Path:
    """Return the user-level global facts file path."""
    base = home if home is not None else Path.home()
    return base / ".zhar" / "facts.json"


def load_facts(path: Path) -> dict[str, str]:
    """Load facts from *path* when it exists, else return an empty mapping."""
    return Facts(path).all() if path.exists() else {}


def load_effective_facts(
    project_path: Path | None = None,
    global_path: Path | None = None,
) -> dict[str, str]:
    """Return merged global and project facts with project values winning."""
    effective: dict[str, str] = {}
    resolved_global_path = global_path if global_path is not None else global_facts_path()
    effective.update(load_facts(resolved_global_path))
    if project_path is not None:
        effective.update(load_facts(project_path))
    return effective


class Facts:
    # %ZHAR:b25f%
    """Persistent string key-value store backed by a single JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, str] = {}
        self._load()

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the value for *key*, or *default* if not present."""
        return self._data.get(key, default)

    def set(self, key: str, value: str) -> None:
        """Set *key* to *value* and persist immediately.

        Raises
        ------
        TypeError
            If *value* is not a ``str``.
        """
        if not isinstance(value, str):
            raise TypeError(
                f"Facts values must be strings, got {type(value).__name__!r} "
                f"for key {key!r}."
            )
        self._data[key] = value
        self._save()

    def unset(self, key: str) -> None:
        """Remove *key* if present and persist.  No-op if key does not exist."""
        if key in self._data:
            del self._data[key]
            self._save()

    def all(self) -> dict[str, str]:
        """Return a shallow copy of all key-value pairs."""
        return dict(self._data)

    # ── internal ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        raw = self._path.read_bytes()
        if raw.strip():
            loaded = orjson.loads(raw)
            # Defensively coerce all values to str in case of manual edits
            self._data = {str(k): str(v) for k, v in loaded.items()}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(orjson.dumps(self._data, option=orjson.OPT_INDENT_2))
