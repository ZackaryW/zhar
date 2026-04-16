"""Tests for repo-centric zhar harness CLI commands."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from zhar.cli import cli
from zhar.harness.getter import list_harness_entries


def _init_project(runner: CliRunner, tmp_path: Path) -> Path:
    """Initialise a .zhar project and return the zhar root."""
    zhar_root = tmp_path / ".zhar"
    result = runner.invoke(cli, ["--root", str(zhar_root), "init"])
    assert result.exit_code == 0, result.output
    return zhar_root


class TestHarnessGet:
    """Validate flattened-key access to mirrored harness files."""

    def test_get_agent_by_flattened_key(self) -> None:
        """`harness get agent-zhar` should print the mirrored agent file."""
        runner = CliRunner()

        result = runner.invoke(cli, ["harness", "get", "agent-zhar"])

        assert result.exit_code == 0, result.output
        assert 'name: zhar-agent' in result.output
        assert 'You are the zhar agent harness specialist.' in result.output

    def test_get_skill_by_flattened_key(self) -> None:
        """`harness get skill-...` should print the mirrored skill file."""
        runner = CliRunner()

        result = runner.invoke(cli, ["harness", "get", "skill-zhar-template-resolution"])

        assert result.exit_code == 0, result.output
        assert 'name: zhar-template-resolution' in result.output
        assert '# zhar Template Resolution' in result.output

    def test_get_help_lists_flattened_keys_with_description_sentence(self) -> None:
        """The get help text should advertise available keys and summaries."""
        runner = CliRunner()
        entries = list_harness_entries()

        result = runner.invoke(cli, ["harness", "get", "--help"], terminal_width=200)

        assert result.exit_code == 0, result.output
        assert 'Available keys:' in result.output
        for entry in entries:
            assert entry.key in result.output
        assert any(entry.kind == 'skill' for entry in entries)
        assert any(
            entry.summary and entry.summary in result.output for entry in entries
        )

    def test_get_unknown_key_fails_with_available_keys(self) -> None:
        """Unknown flattened keys should produce a helpful error."""
        runner = CliRunner()
        entries = list_harness_entries()

        result = runner.invoke(cli, ["harness", "get", "skill-missing"])

        assert result.exit_code != 0
        assert 'Unknown harness file' in result.output
        assert entries[0].key in result.output


class TestHarnessContextExport:
    """Validate legacy memory-context export through the harness group."""

    def test_export_mem_context_writes_requested_file(self, tmp_path: Path) -> None:
        """`harness export-mem-context` should write a context snapshot file."""
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        out_path = tmp_path / '.github' / 'agents' / 'zhar-context.agent.md'

        add_result = runner.invoke(
            cli,
            [
                '--root',
                str(zhar_root),
                'add',
                'project_dna',
                'core_goal',
                'Build zhar',
            ],
        )
        assert add_result.exit_code == 0, add_result.output

        result = runner.invoke(
            cli,
            [
                '--root',
                str(zhar_root),
                'harness',
                'export-mem-context',
                '--out',
                str(out_path),
            ],
        )

        assert result.exit_code == 0, result.output
        assert out_path.exists()
        content = out_path.read_text(encoding='utf-8')
        assert 'Build zhar' in content
        assert 'Memory snapshot' in content

    def test_install_context_alias_writes_requested_file(self, tmp_path: Path) -> None:
        """`harness install context` should delegate to export-mem-context."""
        runner = CliRunner()
        zhar_root = _init_project(runner, tmp_path)
        out_path = tmp_path / '.github' / 'agents' / 'legacy-context.agent.md'

        add_result = runner.invoke(
            cli,
            [
                '--root',
                str(zhar_root),
                'add',
                'project_dna',
                'core_goal',
                'Ship repo harness files',
            ],
        )
        assert add_result.exit_code == 0, add_result.output

        result = runner.invoke(
            cli,
            [
                '--root',
                str(zhar_root),
                'harness',
                'install',
                'context',
                '--out',
                str(out_path),
            ],
        )

        assert result.exit_code == 0, result.output
        assert out_path.exists()
        assert 'Ship repo harness files' in out_path.read_text(encoding='utf-8')