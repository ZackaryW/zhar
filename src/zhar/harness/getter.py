"""Flattened-key lookup helpers for mirrored harness files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from zhar.harness.paths import harness_files_root


@dataclass(frozen=True)
class HarnessEntry:
    """Metadata for one mirrored harness file addressable by a flattened key."""

    key: str
    kind: str
    path: Path
    description: str
    summary: str


def _strip_known_suffix(filename: str, suffix: str) -> str:
    """Remove a known suffix from *filename* and return the remaining stem."""
    if filename.endswith(suffix):
        return filename[: -len(suffix)]
    return Path(filename).stem


def _extract_frontmatter(text: str) -> dict[str, str]:
    """Parse a minimal YAML frontmatter block into a string mapping."""
    if not text.startswith("---\n"):
        return {}

    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}

    fields: dict[str, str] = {}
    for line in parts[0].splitlines()[1:]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields


def _first_sentence(text: str) -> str:
    """Return the first sentence-like fragment from *text* for help summaries."""
    stripped = text.strip()
    if not stripped:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", stripped, maxsplit=1)
    return parts[0]


def _entry_from_file(kind: str, path: Path) -> HarnessEntry:
    """Build a harness entry from one mirrored file on disk."""
    text = path.read_text(encoding="utf-8")
    frontmatter = _extract_frontmatter(text)
    description = frontmatter.get("description", "")

    if kind == "agent":
        slug = _strip_known_suffix(path.name, ".agent.md")
    elif kind == "instruction":
        slug = _strip_known_suffix(path.name, ".instructions.md")
    elif kind == "skill":
        slug = path.parent.name
    else:
        slug = path.stem

    return HarnessEntry(
        key=f"{kind}-{slug}",
        kind=kind,
        path=path,
        description=description,
        summary=_first_sentence(description),
    )


def list_harness_entries(base_dir: Path | None = None) -> list[HarnessEntry]:
    """Return every mirrored harness file addressable through `harness get`."""
    root = harness_files_root(base_dir)
    entries: list[HarnessEntry] = []

    for path in sorted((root / "agents").glob("*.agent.md")):
        entries.append(_entry_from_file("agent", path))
    for path in sorted((root / "instructions").glob("*.instructions.md")):
        entries.append(_entry_from_file("instruction", path))
    for path in sorted((root / "skills").glob("*/SKILL.md")):
        entries.append(_entry_from_file("skill", path))

    return sorted(entries, key=lambda entry: entry.key)


def get_harness_entry(key: str, base_dir: Path | None = None) -> HarnessEntry:
    """Return the mirrored harness entry addressed by *key*."""
    entries = {entry.key: entry for entry in list_harness_entries(base_dir)}
    try:
        return entries[key]
    except KeyError as exc:
        available = ", ".join(sorted(entries)) or "<none>"
        raise KeyError(f"Unknown harness file {key!r}. Available keys: {available}") from exc


def read_harness_file(key: str, base_dir: Path | None = None) -> str:
    """Return the mirrored harness file content addressed by *key*."""
    return get_harness_entry(key, base_dir).path.read_text(encoding="utf-8")