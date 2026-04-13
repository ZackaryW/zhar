"""Filesystem helpers for zhar."""
from __future__ import annotations

from pathlib import Path


def ensure_gitignore_entry(directory: Path, entry: str) -> None:
    """Add *entry* to ``directory/.gitignore`` if it is not already present.

    Creates the file if it does not exist.  The entry is written on its own
    line with a trailing newline.
    """
    gi = directory / ".gitignore"
    if gi.exists():
        lines = gi.read_text(encoding="utf-8").splitlines()
        if entry in lines:
            return  # already present — nothing to do
        # Append with a leading newline if the file doesn't end with one
        existing = gi.read_text(encoding="utf-8")
        sep = "" if existing.endswith("\n") else "\n"
        gi.write_text(existing + sep + entry + "\n", encoding="utf-8")
    else:
        gi.write_text(entry + "\n", encoding="utf-8")
