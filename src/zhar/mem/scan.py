"""Source file marker scanner.

Markers take the form ``%ZHAR:<id>%`` and can appear anywhere on a line
(typically in a comment).  The scanner links source locations back to nodes
so the memory stays anchored to the code that motivated it.

Source field format after sync::

    <relative-path>::<line>::%ZHAR:<id>%

Example::

    src/zhar/mem/node.py::42::%ZHAR:a1b2%
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zhar.mem.node import patch_node
from zhar.mem.store import MemStore

# Marker pattern: %ZHAR:<hex-id>%
_MARKER_RE = re.compile(r"%ZHAR:([0-9a-f]+)%")

# Default file extensions scanned by scan_tree
DEFAULT_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".go", ".rs", ".java", ".kt", ".swift",
    ".c", ".cpp", ".h", ".hpp",
    ".md", ".txt", ".yaml", ".yml", ".toml",
})


@dataclass(frozen=True)
class MarkerHit:
    """One marker found in a source file."""
    path: Path
    line: int       # 1-based
    node_id: str


# ── file-level scanner ────────────────────────────────────────────────────────

def scan_file(path: Path) -> list[MarkerHit]:
    """Return all MarkerHit objects found in *path*.

    Returns an empty list if the file does not exist or cannot be read.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, OSError):
        return []

    hits: list[MarkerHit] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _MARKER_RE.finditer(line):
            hits.append(MarkerHit(path=path, line=lineno, node_id=m.group(1)))
    return hits


# ── tree scanner ──────────────────────────────────────────────────────────────

def scan_tree(
    root: Path,
    extensions: frozenset[str] | set[str] | None = None,
) -> list[MarkerHit]:
    """Recursively scan *root* for marker hits.

    Hidden directories (names starting with ``.``) are skipped.
    """
    exts = frozenset(extensions) if extensions is not None else DEFAULT_EXTENSIONS
    hits: list[MarkerHit] = []

    for path in _iter_files(root, exts):
        hits.extend(scan_file(path))
    return hits


def _iter_files(root: Path, exts: frozenset[str]):
    """Walk *root* skipping hidden directories."""
    for child in sorted(root.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_dir():
            yield from _iter_files(child, exts)
        elif child.is_file() and child.suffix in exts:
            yield child


# ── source sync ───────────────────────────────────────────────────────────────

def sync_sources(
    store: MemStore,
    hits: list[MarkerHit],
) -> dict[str, Any]:
    """Patch the ``source`` field of nodes that appear in *hits*.

    Source format: ``<path>::<line>::%ZHAR:<id>%``

    Returns a report dict with ``updated`` and ``skipped`` counts.
    """
    updated = 0
    skipped = 0

    for hit in hits:
        node = store.get(hit.node_id)
        if node is None:
            skipped += 1
            continue
        source_str = f"{hit.path.as_posix()}::{hit.line}::%ZHAR:{hit.node_id}%"
        patched = patch_node(node, source=source_str)
        store.save(patched)
        updated += 1

    return {"updated": updated, "skipped": skipped}
