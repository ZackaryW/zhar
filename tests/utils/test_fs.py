"""TDD: zhar.utils.fs — filesystem helpers."""
from pathlib import Path
import pytest
from zhar.utils.fs import ensure_gitignore_entry


class TestEnsureGitignoreEntry:
    def test_creates_gitignore_when_missing(self, tmp_path):
        ensure_gitignore_entry(tmp_path, ".zhar/")
        gi = tmp_path / ".gitignore"
        assert gi.exists()
        assert ".zhar/" in gi.read_text()

    def test_appends_entry_to_existing_gitignore(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
        ensure_gitignore_entry(tmp_path, ".zhar/")
        content = gi.read_text()
        assert ".zhar/" in content
        assert "*.pyc" in content  # existing entries preserved

    def test_does_not_duplicate_entry(self, tmp_path):
        gi = tmp_path / ".gitignore"
        gi.write_text(".zhar/\n", encoding="utf-8")
        ensure_gitignore_entry(tmp_path, ".zhar/")
        content = gi.read_text()
        assert content.count(".zhar/") == 1

    def test_entry_on_own_line(self, tmp_path):
        ensure_gitignore_entry(tmp_path, ".zhar/")
        lines = (tmp_path / ".gitignore").read_text().splitlines()
        assert ".zhar/" in lines
