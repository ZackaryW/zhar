"""Tests for `zhar agent get` CLI command.

`zhar agent get --skill <name>` and `zhar agent get --instruction <name>`
render the installed item from its bucket source at runtime, with the current
workspace facts compiled in and %%ZHAR.RSKILL%% tokens fully resolved.

This is distinct from `zhar stack sync` which:
  - Writes output files to disk
  - Leaves %%ZHAR.RSKILL%% verbatim in agent/instruction/hook output
  - Only expands %%ZHAR.RSKILL%% when the item kind is 'skill'

`agent get` always renders with expand_skills=True against the live workspace
facts, and prints the result to stdout (no file written).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from zhar.cli import cli


# ── helpers ───────────────────────────────────────────────────────────────────

def _init_project(runner: CliRunner, tmp_path: Path) -> Path:
    """Initialise a .zhar project and return the zhar root."""
    zhar_root = tmp_path / ".zhar"
    result = runner.invoke(cli, ["--root", str(zhar_root), "init"])
    assert result.exit_code == 0, result.output
    return zhar_root


def _write_registry(zhar_root: Path, entries: dict) -> None:
    cfg = zhar_root / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "stack.json").write_text(json.dumps(entries, indent=2))


def _write_facts(zhar_root: Path, facts: dict) -> None:
    (zhar_root / "facts.json").write_text(json.dumps(facts))


def _write_bucket_file(cache_root: Path, repo: str, branch: str, rel_path: str, content: str) -> None:
    """Write a file into a fake bucket cache directory and keep index.json current."""
    owner, name = repo.split("/", 1)
    folder = f"{owner}_{name}_{branch}"
    dest = cache_root / folder / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    # Maintain index.json so BucketManager.path_for() can resolve without zuu
    import json as _json
    index_path = cache_root / "index.json"
    index = _json.loads(index_path.read_text()) if index_path.exists() else {}
    index[folder] = {"repository": repo, "branch": branch, "last_updated_at": 0.0}
    index_path.write_text(_json.dumps(index, indent=2))


# ── basic output ──────────────────────────────────────────────────────────────

class TestAgentGetBasic:
    def test_get_instruction_prints_to_stdout(self, tmp_path):
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        _write_bucket_file(cache, "org/repo", "main", "instructions/base.md", "follow these rules\n")
        _write_registry(zhar_root, {
            "base-instr": {
                "repo": "org/repo", "branch": "main",
                "kind": "instruction", "source_path": "instructions/base.md",
                "installed_at": "2026-01-01T00:00:00"
            }
        })

        result = runner.invoke(cli, [
            "--root", str(zhar_root),
            "agent", "get", "base-instr",
            "--cache-dir", str(cache),
        ])

        assert result.exit_code == 0, result.output
        assert "follow these rules" in result.output

    def test_get_skill_prints_to_stdout(self, tmp_path):
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        _write_bucket_file(cache, "org/repo", "main", "skills/tool.md", "skill content\n")
        _write_registry(zhar_root, {
            "my-skill": {
                "repo": "org/repo", "branch": "main",
                "kind": "skill", "source_path": "skills/tool.md",
                "installed_at": "2026-01-01T00:00:00"
            }
        })

        result = runner.invoke(cli, [
            "--root", str(zhar_root),
            "agent", "get", "my-skill",
            "--cache-dir", str(cache),
        ])

        assert result.exit_code == 0, result.output
        assert "skill content" in result.output

    def test_get_unknown_name_fails(self, tmp_path):
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        _write_registry(zhar_root, {})

        result = runner.invoke(cli, [
            "--root", str(zhar_root),
            "agent", "get", "ghost",
            "--cache-dir", str(tmp_path / "cache"),
        ])

        assert result.exit_code != 0


# ── facts are compiled in ─────────────────────────────────────────────────────

class TestAgentGetFacts:
    def test_facts_substituted_in_output(self, tmp_path):
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        src = "%%ZHAR.FACT(lang == python)%%\n%%ZHAR.RTEXT_START%%\nPython!\n%%ZHAR.RTEXT_END%%\n"
        _write_bucket_file(cache, "org/repo", "main", "agents/base.md", src)
        _write_registry(zhar_root, {
            "base": {
                "repo": "org/repo", "branch": "main",
                "kind": "agent", "source_path": "agents/base.md",
                "installed_at": "2026-01-01T00:00:00"
            }
        })
        _write_facts(zhar_root, {"lang": "python"})

        result = runner.invoke(cli, [
            "--root", str(zhar_root),
            "agent", "get", "base",
            "--cache-dir", str(cache),
        ])

        assert result.exit_code == 0, result.output
        assert "Python!" in result.output

    def test_false_fact_suppresses_block(self, tmp_path):
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        src = "%%ZHAR.FACT(lang == ruby)%%\n%%ZHAR.RTEXT_START%%\nRuby!\n%%ZHAR.RTEXT_END%%\n"
        _write_bucket_file(cache, "org/repo", "main", "agents/base.md", src)
        _write_registry(zhar_root, {
            "base": {
                "repo": "org/repo", "branch": "main",
                "kind": "agent", "source_path": "agents/base.md",
                "installed_at": "2026-01-01T00:00:00"
            }
        })
        _write_facts(zhar_root, {"lang": "python"})

        result = runner.invoke(cli, [
            "--root", str(zhar_root),
            "agent", "get", "base",
            "--cache-dir", str(cache),
        ])

        assert result.exit_code == 0, result.output
        assert "Ruby!" not in result.output


# ── RSKILL verbatim on get (any kind); RCHUNK always expanded ────────────────

class TestAgentGetSkillExpansion:
    def test_rskill_in_agent_left_verbatim_at_get_time(self, tmp_path):
        """agent get leaves %%ZHAR.RSKILL%% verbatim for any kind.

        Only RCHUNK is expanded inline; RSKILL tokens are kept as references
        so the consumer can see exactly which skills are depended on.
        """
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        agent_src = "preamble\n%%ZHAR.RSKILL(helper)%%\npostamble\n"
        _write_bucket_file(cache, "org/repo", "main", "agents/base.md", agent_src)
        _write_registry(zhar_root, {
            "base": {
                "repo": "org/repo", "branch": "main",
                "kind": "agent", "source_path": "agents/base.md",
                "installed_at": "2026-01-01T00:00:00"
            }
        })

        result = runner.invoke(cli, [
            "--root", str(zhar_root),
            "agent", "get", "base",
            "--cache-dir", str(cache),
        ])

        assert result.exit_code == 0, result.output
        assert "%%ZHAR.RSKILL(helper)%%" in result.output
        assert "preamble" in result.output
        assert "postamble" in result.output

    def test_rskill_in_skill_left_verbatim_at_get_time(self, tmp_path):
        """agent get on a skill also leaves RSKILL verbatim — only sync expands."""
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        src = "%%ZHAR.RSKILL(nested-skill)%%\n"
        _write_bucket_file(cache, "org/repo", "main", "skills/tool.md", src)
        _write_registry(zhar_root, {
            "tool": {
                "repo": "org/repo", "branch": "main",
                "kind": "skill", "source_path": "skills/tool.md",
                "installed_at": "2026-01-01T00:00:00"
            }
        })

        result = runner.invoke(cli, [
            "--root", str(zhar_root),
            "agent", "get", "tool",
            "--cache-dir", str(cache),
        ])

        assert result.exit_code == 0, result.output
        assert "%%ZHAR.RSKILL(nested-skill)%%" in result.output

    def test_rchunk_in_agent_expanded_at_get_time(self, tmp_path):
        """RCHUNK is always expanded on agent get, regardless of kind."""
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        agent_src = "%%ZHAR.RCHUNK(common/header.md)%%\nbody\n"
        _write_bucket_file(cache, "org/repo", "main", "agents/base.md", agent_src)
        _write_bucket_file(cache, "org/repo", "main", "common/header.md", "HEADER\n")
        _write_registry(zhar_root, {
            "base": {
                "repo": "org/repo", "branch": "main",
                "kind": "agent", "source_path": "agents/base.md",
                "installed_at": "2026-01-01T00:00:00"
            }
        })

        result = runner.invoke(cli, [
            "--root", str(zhar_root),
            "agent", "get", "base",
            "--cache-dir", str(cache),
        ])

        assert result.exit_code == 0, result.output
        assert "HEADER" in result.output
        assert "%%ZHAR.RCHUNK" not in result.output
