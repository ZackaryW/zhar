"""Tests for src/zhar/stack/bucket.py

BucketManager wraps GhCacheDir (from zuu) and stores cached repos at
~/.zhar/stack/ globally.  The public surface:

  BucketManager(cache_dir: Path)           # default: Path.home() / ".zhar" / "stack"
  .add(repo: str, branch: str = "main") -> Path     # ensure cached, return path
  .path_for(repo: str, branch: str) -> Path         # resolve without pulling
  .list_repos() -> list[dict]                        # [{repo, branch, last_updated_at}]
  .remove(repo: str, branch: str) -> bool            # delete cached dir + index entry

GhCacheDir is injected (duck-typed) so tests can substitute a fake.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zhar.stack.bucket import BucketManager


# ── fake GhCacheDir ───────────────────────────────────────────────────────────

class FakeGhCacheDir:
    """Minimal GhCacheDir lookalike backed by tmp directories."""

    def __init__(self, cache_dir: Path) -> None:
        self.path = cache_dir
        self.path.mkdir(parents=True, exist_ok=True)
        self._index: dict = {}

    def cache_folder_name(self, repo: str, branch: str) -> str:
        owner, name = repo.split("/", 1)
        return f"{owner}_{name}_{branch.replace('/', '_')}"

    def cache_path_for(self, repo: str, branch: str) -> Path:
        return self.path / self.cache_folder_name(repo, branch)

    def ensure(self, repo: str, branch: str = "main") -> Path:
        p = self.cache_path_for(repo, branch)
        p.mkdir(parents=True, exist_ok=True)
        key = self.cache_folder_name(repo, branch)
        self._index[key] = {"repository": repo, "branch": branch, "last_updated_at": 1000.0}
        self._flush_index()
        return p

    def resolve_cached_repo_path(self, repo: str, branch: str | None = None) -> Path:
        for key, entry in self._index.items():
            if entry["repository"] == repo:
                if branch is None or entry["branch"] == branch:
                    p = self.path / key
                    if p.exists():
                        return p
        raise FileNotFoundError(f"No cached repo for {repo!r}")

    def _flush_index(self) -> None:
        (self.path / "index.json").write_text(
            json.dumps(self._index, indent=2), encoding="utf-8"
        )

    def _read_index(self) -> dict:
        idx_path = self.path / "index.json"
        if not idx_path.exists():
            return {}
        return json.loads(idx_path.read_text(encoding="utf-8"))


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "stack"


@pytest.fixture
def fake_gh(cache_dir: Path) -> FakeGhCacheDir:
    return FakeGhCacheDir(cache_dir)


@pytest.fixture
def manager(cache_dir: Path, fake_gh: FakeGhCacheDir) -> BucketManager:
    return BucketManager(cache_dir=cache_dir, _gh=fake_gh)


# ── construction ──────────────────────────────────────────────────────────────

class TestConstruction:
    def test_default_cache_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Default cache_dir is ~/.zhar/stack/ (zuu import is bypassed via _gh)."""
        fake = FakeGhCacheDir(tmp_path / "stack")
        bm = BucketManager(cache_dir=None, _gh=fake)
        # cache_dir should be ~/.zhar/stack when no override given
        assert bm.cache_dir == Path.home() / ".zhar" / "stack"

    def test_custom_cache_dir(self, cache_dir: Path, fake_gh: FakeGhCacheDir):
        bm = BucketManager(cache_dir=cache_dir, _gh=fake_gh)
        assert bm.cache_dir == cache_dir


# ── add ───────────────────────────────────────────────────────────────────────

class TestAdd:
    def test_add_returns_path(self, manager: BucketManager):
        p = manager.add("org/repo")
        assert p.exists()

    def test_add_default_branch_main(self, manager: BucketManager, fake_gh: FakeGhCacheDir):
        manager.add("org/repo")
        key = fake_gh.cache_folder_name("org/repo", "main")
        assert key in fake_gh._read_index()

    def test_add_custom_branch(self, manager: BucketManager, fake_gh: FakeGhCacheDir):
        manager.add("org/repo", branch="dev")
        key = fake_gh.cache_folder_name("org/repo", "dev")
        assert key in fake_gh._read_index()

    def test_add_idempotent(self, manager: BucketManager):
        p1 = manager.add("org/repo")
        p2 = manager.add("org/repo")
        assert p1 == p2


# ── path_for ──────────────────────────────────────────────────────────────────

class TestPathFor:
    def test_path_for_existing(self, manager: BucketManager):
        manager.add("org/repo")
        p = manager.path_for("org/repo")
        assert p.exists()

    def test_path_for_missing_raises(self, manager: BucketManager):
        with pytest.raises(FileNotFoundError):
            manager.path_for("org/nonexistent")

    def test_path_for_with_branch(self, manager: BucketManager):
        manager.add("org/repo", branch="dev")
        p = manager.path_for("org/repo", branch="dev")
        assert p.exists()


# ── list_repos ────────────────────────────────────────────────────────────────

class TestListRepos:
    def test_empty_when_no_buckets(self, manager: BucketManager):
        assert manager.list_repos() == []

    def test_lists_added_repos(self, manager: BucketManager):
        manager.add("org/alpha")
        manager.add("org/beta", branch="dev")
        repos = manager.list_repos()
        repo_names = [r["repo"] for r in repos]
        assert "org/alpha" in repo_names
        assert "org/beta" in repo_names

    def test_entry_has_required_keys(self, manager: BucketManager):
        manager.add("org/repo")
        entry = manager.list_repos()[0]
        assert "repo" in entry
        assert "branch" in entry
        assert "last_updated_at" in entry


# ── remove ────────────────────────────────────────────────────────────────────

class TestRemove:
    def test_remove_existing(self, manager: BucketManager):
        manager.add("org/repo")
        result = manager.remove("org/repo")
        assert result is True

    def test_remove_clears_from_list(self, manager: BucketManager):
        manager.add("org/repo")
        manager.remove("org/repo")
        repos = manager.list_repos()
        assert not any(r["repo"] == "org/repo" for r in repos)

    def test_remove_nonexistent_returns_false(self, manager: BucketManager):
        result = manager.remove("org/ghost")
        assert result is False

    def test_remove_deletes_directory(self, manager: BucketManager, fake_gh: FakeGhCacheDir):
        p = manager.add("org/repo")
        assert p.exists()
        manager.remove("org/repo")
        assert not p.exists()
