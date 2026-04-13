"""BucketManager — TTL-based GitHub repo cache for zhar stack buckets.

Wraps ``zuu.GhCacheDir`` (or any compatible duck-type) and stores cached
repositories globally at ``~/.zhar/stack/``.  Per-project state (which
buckets are installed) lives in ``.zhar/cfg/stack.json`` and is managed
by ``StackRegistry``.

Public API
----------
  BucketManager(cache_dir: Path | None, _gh=None)
  .add(repo, branch="main") -> Path      ensure cached, return repo root
  .path_for(repo, branch=None) -> Path   resolve without pulling
  .list_repos() -> list[dict]            [{repo, branch, last_updated_at}, ...]
  .remove(repo, branch=None) -> bool     delete cached dir + index entry
"""
# %ZHAR:6f2b% %ZHAR:21fd%
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


# ── lazy zuu import ───────────────────────────────────────────────────────────

def _make_gh_cache_dir(cache_dir: Path) -> Any:
    """Instantiate a real GhCacheDir, importing zuu lazily."""
    try:
        from zuu.v202602_1.gh_cache_dir import GhCacheDir  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "zuu is required for zhar stack bucket management. "
            "Install it with: uv add zuu"
        ) from exc
    # TTL: 1 hour (3600 s) between update checks
    return GhCacheDir(cache_dir, minimum_ttc_time_to_check_seconds=3600)


# ── BucketManager ─────────────────────────────────────────────────────────────

_DEFAULT_CACHE_DIR = Path.home() / ".zhar" / "stack"


class BucketManager:
    """Manage a collection of GitHub repo caches (buckets) for zhar stack.

    Parameters
    ----------
    cache_dir:
        Directory where cached repositories are stored.
        Defaults to ``~/.zhar/stack/``.
    _gh:
        Optional pre-built GhCacheDir-compatible object.  Used by tests to
        inject a fake without touching the filesystem or network.
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        *,
        _gh: Any = None,
    ) -> None:
        self.cache_dir: Path = Path(cache_dir) if cache_dir is not None else _DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._gh = _gh if _gh is not None else _make_gh_cache_dir(self.cache_dir)

    # ── public API ────────────────────────────────────────────────────────────

    def add(self, repo: str, branch: str = "main") -> Path:
        """Ensure *repo* at *branch* is cached and return the local root path.

        Calls ``GhCacheDir.ensure()`` which clones the repo on first call and
        runs ``git pull --ff-only`` when the TTL has elapsed.
        """
        return self._gh.ensure(repo, branch)

    def path_for(self, repo: str, branch: str | None = None) -> Path:
        """Return the cached local path for *repo* without triggering a pull.

        Raises
        ------
        FileNotFoundError
            If *repo* (and optionally *branch*) is not in the cache.
        """
        return self._gh.resolve_cached_repo_path(repo, branch)

    def list_repos(self) -> list[dict[str, Any]]:
        """Return metadata for every entry in the index.

        Each item has at least ``repo``, ``branch``, and ``last_updated_at``
        keys.  Only entries whose local directory still exists are returned.
        """
        index = self._read_index()
        results: list[dict[str, Any]] = []
        for folder_name, entry in index.items():
            repo = entry.get("repository") or entry.get("repo", "")
            branch = entry.get("branch", "main")
            last_updated = entry.get("last_updated_at")
            cache_path = self.cache_dir / folder_name
            if not cache_path.exists():
                continue
            results.append({
                "repo": repo,
                "branch": branch,
                "last_updated_at": last_updated,
                "local_path": cache_path,
            })
        return results

    def remove(self, repo: str, branch: str | None = None) -> bool:
        """Delete the cached directory for *repo* and remove it from the index.

        Returns ``True`` if an entry was found and deleted, ``False`` if not
        found (no-op).
        """
        index = self._read_index()
        keys_to_remove: list[str] = []
        for folder_name, entry in index.items():
            repo_val = entry.get("repository") or entry.get("repo", "")
            branch_val = entry.get("branch")
            if repo_val != repo:
                continue
            if branch is not None and branch_val != branch:
                continue
            keys_to_remove.append(folder_name)

        if not keys_to_remove:
            return False

        for key in keys_to_remove:
            cache_path = self.cache_dir / key
            if cache_path.exists():
                shutil.rmtree(cache_path)
            del index[key]

        self._write_index(index)
        return True

    # ── internal ──────────────────────────────────────────────────────────────

    @property
    def _index_path(self) -> Path:
        return self.cache_dir / "index.json"

    def _read_index(self) -> dict[str, dict[str, Any]]:
        if not self._index_path.exists():
            return {}
        return json.loads(self._index_path.read_text(encoding="utf-8"))

    def _write_index(self, index: dict[str, dict[str, Any]]) -> None:
        self._index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True),
            encoding="utf-8",
        )
