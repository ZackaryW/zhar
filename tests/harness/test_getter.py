"""Tests for repo-centric harness file discovery and reading."""

from __future__ import annotations

import pytest

from zhar.harness.getter import get_harness_entry, list_harness_entries, read_harness_file


class TestHarnessGetter:
    """Validate mirrored harness file indexing."""

    def test_list_harness_entries_includes_expected_flattened_keys(self) -> None:
        """The mirrored harness file tree should expose stable flattened keys."""
        entries = list_harness_entries()

        keys = {entry.key for entry in entries}
        assert 'agent-zhar' in keys
        assert 'instruction-zhar-memory' in keys
        assert 'instruction-zhar-stack' in keys
        assert 'instruction-zhar-agent-get' in keys
        assert 'skill-zhar-template-resolution' in keys

    def test_get_harness_entry_uses_first_description_sentence(self) -> None:
        """Entry summaries should be derived from the frontmatter description."""
        entry = get_harness_entry('skill-zhar-template-resolution')

        assert entry.summary.startswith('Use when debugging or explaining zhar template rendering')
        assert entry.path.name == 'SKILL.md'

    def test_read_harness_file_returns_file_content(self) -> None:
        """Harness file lookup should return the mirrored file body."""
        content = read_harness_file('instruction-zhar-memory')

        assert '# zhar Memory Workflow' in content

    def test_unknown_key_raises_key_error(self) -> None:
        """Unknown flattened keys should raise a clear lookup error."""
        with pytest.raises(KeyError):
            get_harness_entry('agent-missing')