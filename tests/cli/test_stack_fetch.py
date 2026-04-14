"""Tests for `zhar stack fetch` CLI command."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from zhar.cli import cli


def _init_project(runner: CliRunner, tmp_path: Path) -> Path:
    """Initialise a .zhar project and return the zhar root."""
    zhar_root = tmp_path / ".zhar"
    result = runner.invoke(cli, ["--root", str(zhar_root), "init"])
    assert result.exit_code == 0, result.output
    return zhar_root


def _write_facts(zhar_root: Path, facts: dict[str, str]) -> None:
    """Write a project facts fixture under *zhar_root*."""
    (zhar_root / "facts.json").write_text(json.dumps(facts), encoding="utf-8")


def _write_bucket_file(cache_root: Path, repo: str, branch: str, rel_path: str, content: str) -> None:
    """Write one file into a fake bucket cache directory and refresh index.json."""
    owner, repo_name = repo.split("/", 1)
    folder = f"{owner}_{repo_name}_{branch}"
    dest = cache_root / folder / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")

    index_path = cache_root / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    index[folder] = {"repository": repo, "branch": branch, "last_updated_at": 0.0}
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def _read_stack_registry(zhar_root: Path) -> dict[str, dict[str, str]]:
    """Read the stack registry fixture under *zhar_root*."""
    registry_path = zhar_root / "cfg" / "stack.json"
    if not registry_path.exists():
        return {}
    return json.loads(registry_path.read_text(encoding="utf-8"))


class TestStackFetch:
    """Validate workspace-ready rendering for `zhar stack fetch`."""

    def test_stack_fetch_reads_cached_skill_directory(self, tmp_path: Path) -> None:
        """`stack fetch` should render a cached `.github/skills/<name>/SKILL.md` source."""
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        source = (
            "%%ZHAR.FACT(lang == python)%%\n"
            "%%ZHAR.RTEXT_START%%\n"
            "Python runtime\n"
            "%%ZHAR.RTEXT_END%%\n"
            "%%ZHAR.RCHUNK(shared/header.md)%%\n"
            "%%ZHAR.RSKILL(helper-skill)%%\n"
        )
        _write_bucket_file(cache, "org/repo", "main", ".github/skills/cline-memory-bank/SKILL.md", source)
        _write_bucket_file(cache, "org/repo", "main", "shared/header.md", "HEADER\n")
        _write_facts(zhar_root, {"lang": "python"})

        stack_result = runner.invoke(
            cli,
            [
                "--root",
                str(zhar_root),
                "stack",
                "fetch",
                "cline-memory-bank",
                "--cache-dir",
                str(cache),
            ],
        )

        assert stack_result.exit_code == 0, stack_result.output
        assert "Python runtime" in stack_result.output
        assert "HEADER" in stack_result.output
        assert "%%ZHAR.RSKILL(helper-skill)%%" in stack_result.output

    def test_stack_fetch_top_fuzzy_match(self, tmp_path: Path) -> None:
        """`stack fetch --fuzzy-conf` should resolve only the top-scoring cached source."""
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        _write_bucket_file(cache, "org/repo", "main", ".github/skills/python-memory-bank/SKILL.md", "PYTHON\n")
        _write_bucket_file(cache, "org/repo", "main", ".github/skills/ruby-memory-bank/SKILL.md", "RUBY\n")

        result = runner.invoke(
            cli,
            [
                "--root",
                str(zhar_root),
                "stack",
                "fetch",
                "pythn-memory-bank",
                "--cache-dir",
                str(cache),
                "--fuzzy-conf",
                "0.70",
            ],
        )

        assert result.exit_code == 0, result.output
        assert result.output == "PYTHON\n"

    def test_stack_fetch_fuzzy_threshold_failure_reports_top_score(self, tmp_path: Path) -> None:
        """`stack fetch --fuzzy-conf` should fail when the top score stays below the threshold."""
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        _write_bucket_file(cache, "org/repo", "main", ".github/skills/python-memory-bank/SKILL.md", "PYTHON\n")

        result = runner.invoke(
            cli,
            [
                "--root",
                str(zhar_root),
                "stack",
                "fetch",
                "zzz",
                "--cache-dir",
                str(cache),
                "--fuzzy-conf",
                "0.95",
            ],
        )

        assert result.exit_code != 0
        assert "Top fuzzy match 'python-memory-bank' scored" in result.output
        assert "below --fuzzy-conf 0.950" in result.output

    def test_stack_fetch_unknown_name_fails_without_fuzzy(self, tmp_path: Path) -> None:
        """`stack fetch` should fail clearly when no cached source matches."""
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)

        result = runner.invoke(
            cli,
            [
                "--root",
                str(zhar_root),
                "stack",
                "fetch",
                "missing",
                "--cache-dir",
                str(tmp_path / "cache"),
            ],
        )

        assert result.exit_code != 0
        assert "No cached stack sources found. Run: zhar stack bucket add <repo>" in result.output


class TestStackInstall:
    """Validate auto-resolution for `zhar stack install`."""

    def test_stack_install_auto_resolves_cached_skill_source(self, tmp_path: Path) -> None:
        """`stack install` should infer the cached skill source path from NAME and KIND."""
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        _write_bucket_file(cache, "org/repo", "main", ".github/skills/cline-memory-bank/SKILL.md", "skill body\n")

        result = runner.invoke(
            cli,
            [
                "--root",
                str(zhar_root),
                "stack",
                "install",
                "cline-memory-bank",
                "org/repo",
                "--kind",
                "skill",
                "--cache-dir",
                str(cache),
            ],
        )

        assert result.exit_code == 0, result.output
        assert ".github/skills/cline-memory-bank/SKILL.md" in result.output
        registry = _read_stack_registry(zhar_root)
        assert registry["cline-memory-bank"]["source_path"] == ".github/skills/cline-memory-bank/SKILL.md"

    def test_stack_install_explicit_source_uses_same_cached_resolution(self, tmp_path: Path) -> None:
        """`stack install --source` should validate explicit paths against cached sources."""
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        cache = tmp_path / "cache"
        _write_bucket_file(cache, "org/repo", "main", ".github/skills/cline-memory-bank/SKILL.md", "skill body\n")

        result = runner.invoke(
            cli,
            [
                "--root",
                str(zhar_root),
                "stack",
                "install",
                "memory-bank",
                "org/repo",
                "--kind",
                "skill",
                "--source",
                ".github/skills/cline-memory-bank/SKILL.md",
                "--cache-dir",
                str(cache),
            ],
        )

        assert result.exit_code == 0, result.output
        registry = _read_stack_registry(zhar_root)
        assert registry["memory-bank"]["source_path"] == ".github/skills/cline-memory-bank/SKILL.md"