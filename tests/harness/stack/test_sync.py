"""Tests for src/zhar/harness/stack/sync.py

sync_stack iterates over installed items in StackRegistry, locates their
source files via BucketManager, renders them through the template engine
with a combined TemplateContext (facts + memory groups), and writes the
output files to the project's output directory.

Public API
----------
  SyncResult dataclass:
    synced: list[str]    names of items successfully written
    skipped: list[str]   names skipped (source missing, dry_run, etc.)
    errors: list[str]    names that raised exceptions (message appended)

  sync_stack(
      registry: StackRegistry,
      bucket_mgr: BucketManager,
      context: TemplateContext,
      output_dir: Path,
      *,
      dry_run: bool = False,
  ) -> SyncResult

Output file mapping by kind:
  agent       → output_dir / "<name>.agent.md"
  instruction → output_dir / "<name>.instructions.md"
  skill       → output_dir / "<name>.skill.md"
  hook        → output_dir / "<name>.hook.md"
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from zhar.harness.stack.registry import StackRegistry
from zhar.harness.stack.sync import SyncResult, sync_stack
from zhar.harness.stack.template import TemplateContext


# ── helpers / fixtures ────────────────────────────────────────────────────────

class FakeBucketManager:
    """BucketManager stub that writes files to a real tmp directory.

    ``files`` is a mapping of ``"org/repo::branch::rel/path"`` → content.
    Each entry is written to ``<cache_root>/<org>_<repo>_<branch>/<rel/path>``.
    """

    def __init__(self, cache_root: Path, files: dict[str, str]) -> None:
        self._root = cache_root
        self._roots: dict[str, Path] = {}  # "org/repo::branch" → dir
        for key, content in files.items():
            repo, branch, rel = key.split("::", 2)
            repo_dir = self._repo_dir(repo, branch)
            target = repo_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def _repo_dir(self, repo: str, branch: str) -> Path:
        key = f"{repo}::{branch}"
        if key not in self._roots:
            owner, name = repo.split("/", 1)
            d = self._root / f"{owner}_{name}_{branch}"
            d.mkdir(parents=True, exist_ok=True)
            self._roots[key] = d
        return self._roots[key]

    def path_for(self, repo: str, branch: str | None = None) -> Path:
        branch = branch or "main"
        d = self._repo_dir(repo, branch)
        if not d.exists():
            raise FileNotFoundError(repo)
        return d


def simple_ctx(facts: dict | None = None) -> TemplateContext:
    return TemplateContext(
        facts=facts or {},
        groups={},
        chunk_resolver=None,  # overridden by sync_stack
    )


@pytest.fixture
def cache_root(tmp_path: Path) -> Path:
    d = tmp_path / "cache"
    d.mkdir()
    return d


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    d = tmp_path / "agents"
    d.mkdir()
    return d


@pytest.fixture
def reg_path(tmp_path: Path) -> Path:
    return tmp_path / "stack.json"


@pytest.fixture
def reg(reg_path: Path) -> StackRegistry:
    return StackRegistry(reg_path)


# ── SyncResult dataclass ──────────────────────────────────────────────────────

class TestSyncResult:
    def test_defaults_empty(self):
        r = SyncResult()
        assert r.synced == []
        assert r.skipped == []
        assert r.errors == []

    def test_total(self):
        r = SyncResult(synced=["a", "b"], skipped=["c"], errors=["d"])
        assert r.total == 4


# ── sync_stack with no items ──────────────────────────────────────────────────

class TestSyncEmpty:
    def test_empty_registry_returns_empty_result(self, reg, output_dir, tmp_path):
        bm = FakeBucketManager(tmp_path / "cache", {})
        result = sync_stack(reg, bm, simple_ctx(), output_dir)
        assert result.synced == []
        assert result.errors == []


# ── sync_stack normal rendering ───────────────────────────────────────────────

class TestSyncRender:
    def test_agent_written_to_correct_path(self, reg, output_dir, tmp_path):
        content = "# Agent\nHello agent.\n"
        bm = FakeBucketManager(tmp_path / "cache",
                               {"org/repo::main::agents/base.md": content})
        reg.install("base", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/base.md")

        result = sync_stack(reg, bm, simple_ctx(), output_dir)

        assert "base" in result.synced
        out_file = output_dir / "base.agent.md"
        assert out_file.exists()
        assert out_file.read_text() == content

    def test_instruction_written_to_correct_path(self, reg, output_dir, tmp_path):
        content = "Follow these rules.\n"
        bm = FakeBucketManager(tmp_path / "cache",
                               {"org/repo::main::instructions/rules.md": content})
        reg.install("rules", repo="org/repo", branch="main",
                    kind="instruction", source_path="instructions/rules.md")

        sync_stack(reg, bm, simple_ctx(), output_dir)

        assert (output_dir / "rules.instructions.md").exists()

    def test_skill_written_to_correct_path(self, reg, output_dir, tmp_path):
        bm = FakeBucketManager(tmp_path / "cache",
                               {"org/repo::main::skills/tool.md": "skill\n"})
        reg.install("tool", repo="org/repo", branch="main",
                    kind="skill", source_path="skills/tool.md")

        sync_stack(reg, bm, simple_ctx(), output_dir)

        assert (output_dir / "tool.skill.md").exists()

    def test_hook_written_to_correct_path(self, reg, output_dir, tmp_path):
        bm = FakeBucketManager(tmp_path / "cache",
                               {"org/repo::main::hooks/pre.sh": "#!/bin/bash\n"})
        reg.install("pre", repo="org/repo", branch="main",
                    kind="hook", source_path="hooks/pre.sh")

        sync_stack(reg, bm, simple_ctx(), output_dir)

        assert (output_dir / "pre.hook.md").exists()

    def test_template_vars_evaluated(self, reg, output_dir, tmp_path):
        """Facts in context should be substituted via template engine."""
        template_src = textwrap.dedent("""\
            %ZO% lang == python
            %TEXT%
            Python project detected.
            %TEXT%
            %ZC%
        """)
        bm = FakeBucketManager(tmp_path / "cache",
                               {"org/repo::main::agents/base.md": template_src})
        reg.install("base", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/base.md")
        ctx = simple_ctx(facts={"lang": "python"})

        sync_stack(reg, bm, ctx, output_dir)

        out = (output_dir / "base.agent.md").read_text()
        assert "Python project detected." in out

    def test_multiple_items_all_synced(self, reg, output_dir, tmp_path):
        bm = FakeBucketManager(tmp_path / "cache", {
            "org/repo::main::agents/a.md": "Agent A\n",
            "org/repo::main::agents/b.md": "Agent B\n",
        })
        reg.install("agent-a", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/a.md")
        reg.install("agent-b", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/b.md")

        result = sync_stack(reg, bm, simple_ctx(), output_dir)

        assert len(result.synced) == 2
        assert result.errors == []


# ── dry_run ───────────────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_does_not_write_files(self, reg, output_dir, tmp_path):
        bm = FakeBucketManager(tmp_path / "cache",
                               {"org/repo::main::agents/base.md": "content\n"})
        reg.install("base", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/base.md")

        result = sync_stack(reg, bm, simple_ctx(), output_dir, dry_run=True)

        assert "base" in result.synced
        assert not (output_dir / "base.agent.md").exists()


# ── error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_missing_source_goes_to_errors(self, reg, output_dir, tmp_path):
        bm = FakeBucketManager(tmp_path / "cache", {})  # no files
        reg.install("missing", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/nonexistent.md")

        result = sync_stack(reg, bm, simple_ctx(), output_dir)

        assert any("missing" in e for e in result.errors)
        assert result.synced == []

    def test_other_items_still_sync_on_error(self, reg, output_dir, tmp_path):
        bm = FakeBucketManager(tmp_path / "cache", {
            "org/repo::main::agents/ok.md": "OK\n",
            # agents/bad.md intentionally absent
        })
        reg.install("ok", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/ok.md")
        reg.install("bad", repo="org/repo", branch="main",
                    kind="agent", source_path="agents/bad.md")

        result = sync_stack(reg, bm, simple_ctx(), output_dir)

        assert "ok" in result.synced
        assert any("bad" in e for e in result.errors)
