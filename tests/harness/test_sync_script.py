"""Tests for the repo-level harness file sync script."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_script_module():
    """Load the root sync script as a Python module for testing."""
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'sync_harness_files.py'
    spec = importlib.util.spec_from_file_location('sync_harness_files', script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestSyncHarnessFilesScript:
    """Validate the repo macro that mirrors .github harness files."""

    def test_sync_harness_files_copies_agents_instructions_and_skills(self, tmp_path: Path) -> None:
        """The script should mirror the supported .github subtrees into harness files."""
        module = _load_script_module()
        source_root = tmp_path / '.github'
        target_root = tmp_path / 'src' / 'zhar' / 'harness' / 'files'

        (source_root / 'agents').mkdir(parents=True)
        (source_root / 'instructions').mkdir(parents=True)
        (source_root / 'skills' / 'demo-skill').mkdir(parents=True)
        (source_root / 'agents' / 'demo.agent.md').write_text('agent body\n', encoding='utf-8')
        (source_root / 'instructions' / 'demo.instructions.md').write_text('instruction body\n', encoding='utf-8')
        (source_root / 'skills' / 'demo-skill' / 'SKILL.md').write_text('skill body\n', encoding='utf-8')

        changed = module.sync_harness_files(source_root, target_root)

        assert any(path.as_posix().endswith('agents/demo.agent.md') for path in changed)
        assert (target_root / 'agents' / 'demo.agent.md').read_text(encoding='utf-8') == 'agent body\n'
        assert (target_root / 'instructions' / 'demo.instructions.md').read_text(encoding='utf-8') == 'instruction body\n'
        assert (target_root / 'skills' / 'demo-skill' / 'SKILL.md').read_text(encoding='utf-8') == 'skill body\n'

    def test_check_harness_files_detects_missing_or_stale_files(self, tmp_path: Path) -> None:
        """Check mode should report drift when the mirror is missing files."""
        module = _load_script_module()
        source_root = tmp_path / '.github'
        target_root = tmp_path / 'src' / 'zhar' / 'harness' / 'files'

        (source_root / 'agents').mkdir(parents=True)
        (source_root / 'agents' / 'demo.agent.md').write_text('agent body\n', encoding='utf-8')

        mismatches = module.check_harness_files(source_root, target_root)

        assert mismatches
        assert any(path.as_posix().endswith('agents/demo.agent.md') for path in mismatches)