"""Mtime-based file cache — prevents redundant disk reads during scan/export."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class _CachedEntry:
    """One cached payload keyed by the file mtime (float seconds) it was read at."""

    mtime: float
    text: str | None = None
    data: bytes | None = None


@dataclass
class MtimeFileCache:
    """Cache text *and* bytes file reads until the file mtime changes on disk.

    Uses ``stat().st_mtime`` (float seconds) as the cache key so that an
    ``os.utime(path, (atime, mtime))`` round-trip correctly invalidates or
    preserves the entry — nanosecond precision (``st_mtime_ns``) would diverge
    after a float-based ``os.utime`` call.

    Both ``read_text`` and ``read_bytes`` share the same per-path entry so a
    single ``invalidate`` clears both representations at once.
    """

    _cache: dict[Path, _CachedEntry] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _stat_or_none(self, path: Path) -> float | None:
        """Return st_mtime float, or None (and purge entry) when file is missing."""
        try:
            return path.stat().st_mtime
        except FileNotFoundError:
            self._cache.pop(path, None)
            return None

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def read_text(self, path: Path, encoding: str = "utf-8") -> str:
        """Return cached text for *path* until its mtime changes.

        Returns ``""`` when the file does not exist or cannot be decoded.
        """
        mtime = self._stat_or_none(path)
        if mtime is None:
            return ""

        entry = self._cache.get(path)
        if entry is not None and entry.mtime == mtime and entry.text is not None:
            return entry.text

        try:
            text = path.read_text(encoding=encoding)
        except (UnicodeDecodeError, OSError):
            self._cache.pop(path, None)
            return ""

        # Preserve any existing bytes payload in the same entry.
        existing_data = entry.data if (entry and entry.mtime == mtime) else None
        self._cache[path] = _CachedEntry(mtime=mtime, text=text, data=existing_data)
        return text

    def read_bytes(self, path: Path) -> bytes:
        """Return cached bytes for *path* until its mtime changes.

        Returns ``b""`` when the file does not exist.
        """
        mtime = self._stat_or_none(path)
        if mtime is None:
            return b""

        entry = self._cache.get(path)
        if entry is not None and entry.mtime == mtime and entry.data is not None:
            return entry.data

        try:
            data = path.read_bytes()
        except OSError:
            self._cache.pop(path, None)
            return b""

        existing_text = entry.text if (entry and entry.mtime == mtime) else None
        self._cache[path] = _CachedEntry(mtime=mtime, text=existing_text, data=data)
        return data

    def invalidate(self, path: Path) -> None:
        """Drop the cached entry for *path* so the next read hits disk."""
        self._cache.pop(path, None)
