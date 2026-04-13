"""Tests for src/zhar/stack/registry.py

StackRegistry manages the per-project manifest of installed stack items.
Persisted at .zhar/cfg/stack.json.

Schema (one entry per installed item):
  {
    "<name>": {
      "repo": "org/repo",
      "branch": "main",
      "kind": "agent" | "instruction" | "skill" | "hook",
      "source_path": "relative/path/in/repo",
      "installed_at": <iso timestamp>
    },
    ...
  }

Public API
----------
  StackRegistry(path: Path)          # path to stack.json
  .install(name, repo, branch, kind, source_path) -> dict
  .uninstall(name) -> bool
  .get(name) -> dict | None
  .list_items() -> list[dict]        # all installed items with "name" key injected
  .is_installed(name) -> bool
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from zhar.stack.registry import StackRegistry


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def reg_path(tmp_path: Path) -> Path:
    return tmp_path / "stack.json"


@pytest.fixture
def reg(reg_path: Path) -> StackRegistry:
    return StackRegistry(reg_path)


# ── construction ──────────────────────────────────────────────────────────────

class TestConstruction:
    def test_file_not_required_on_init(self, reg_path: Path):
        r = StackRegistry(reg_path)
        assert not reg_path.exists()  # lazy — only written on mutation

    def test_list_empty_when_no_file(self, reg: StackRegistry):
        assert reg.list_items() == []


# ── install ───────────────────────────────────────────────────────────────────

class TestInstall:
    def test_install_creates_entry(self, reg: StackRegistry):
        reg.install("my-agent", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/base.md")
        assert reg.is_installed("my-agent")

    def test_install_persists_to_disk(self, reg: StackRegistry, reg_path: Path):
        reg.install("my-agent", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/base.md")
        assert reg_path.exists()
        data = json.loads(reg_path.read_text())
        assert "my-agent" in data

    def test_install_returns_entry_dict(self, reg: StackRegistry):
        entry = reg.install("my-agent", repo="org/repo", branch="main",
                            kind="agent", source_path="agents/base.md")
        assert entry["repo"] == "org/repo"
        assert entry["branch"] == "main"
        assert entry["kind"] == "agent"
        assert entry["source_path"] == "agents/base.md"
        assert "installed_at" in entry

    def test_install_overwrites_existing(self, reg: StackRegistry):
        reg.install("my-agent", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/v1.md")
        reg.install("my-agent", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/v2.md")
        entry = reg.get("my-agent")
        assert entry["source_path"] == "agents/v2.md"

    def test_install_multiple_items(self, reg: StackRegistry):
        reg.install("agent-a", repo="org/repo", branch="main",
                    kind="agent", source_path="a.md")
        reg.install("hook-b", repo="org/repo", branch="main",
                    kind="hook", source_path="b.sh")
        assert len(reg.list_items()) == 2

    def test_install_invalid_kind_raises(self, reg: StackRegistry):
        with pytest.raises(ValueError, match="kind"):
            reg.install("x", repo="org/repo", branch="main",
                        kind="unknown", source_path="x.md")


# ── uninstall ─────────────────────────────────────────────────────────────────

class TestUninstall:
    def test_uninstall_existing(self, reg: StackRegistry):
        reg.install("my-agent", repo="org/repo", branch="main",
                    kind="agent", source_path="a.md")
        result = reg.uninstall("my-agent")
        assert result is True
        assert not reg.is_installed("my-agent")

    def test_uninstall_nonexistent_returns_false(self, reg: StackRegistry):
        assert reg.uninstall("ghost") is False

    def test_uninstall_persists(self, reg: StackRegistry, reg_path: Path):
        reg.install("my-agent", repo="org/repo", branch="main",
                    kind="agent", source_path="a.md")
        reg.uninstall("my-agent")
        data = json.loads(reg_path.read_text())
        assert "my-agent" not in data


# ── get ───────────────────────────────────────────────────────────────────────

class TestGet:
    def test_get_existing(self, reg: StackRegistry):
        reg.install("my-agent", repo="org/repo", branch="main",
                    kind="agent", source_path="a.md")
        entry = reg.get("my-agent")
        assert entry is not None
        assert entry["kind"] == "agent"

    def test_get_missing_returns_none(self, reg: StackRegistry):
        assert reg.get("ghost") is None


# ── list_items ────────────────────────────────────────────────────────────────

class TestListItems:
    def test_name_key_injected(self, reg: StackRegistry):
        reg.install("my-agent", repo="org/repo", branch="main",
                    kind="agent", source_path="a.md")
        items = reg.list_items()
        assert items[0]["name"] == "my-agent"

    def test_sorted_by_name(self, reg: StackRegistry):
        reg.install("zzz", repo="org/r", branch="main", kind="hook", source_path="z.sh")
        reg.install("aaa", repo="org/r", branch="main", kind="agent", source_path="a.md")
        names = [i["name"] for i in reg.list_items()]
        assert names == sorted(names)

    def test_all_fields_present(self, reg: StackRegistry):
        reg.install("x", repo="org/r", branch="dev", kind="skill", source_path="s.md")
        item = reg.list_items()[0]
        for key in ("name", "repo", "branch", "kind", "source_path", "installed_at"):
            assert key in item


# ── reload from disk ──────────────────────────────────────────────────────────

class TestPersistence:
    def test_reload_from_disk(self, reg_path: Path):
        r1 = StackRegistry(reg_path)
        r1.install("my-agent", repo="org/repo", branch="main",
                   kind="agent", source_path="a.md")
        # fresh instance reads from same file
        r2 = StackRegistry(reg_path)
        assert r2.is_installed("my-agent")
