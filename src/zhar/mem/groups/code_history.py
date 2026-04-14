"""Built-in group: code_history — code-level change records.

Node types
----------
file_change       A significant change to a file.
function_change   A change to a specific function or method.
breaking_change   A change that breaks existing callers or contracts.
revert_note       A record of a revert and why it was made.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from zhar.mem.group import GroupDef, NodeTypeDef, RuntimeContextProvider, RuntimeContextRequest


@dataclass
class FileChangeMeta:
    """Metadata for a file-level code change record.

    ``path`` is retained as a legacy fallback for older records, but once a
    node is source-linked via ``source`` it becomes redundant and is stripped
    before persistence.
    """

    agent: str = ""
    commit_hash: str = ""
    path: str = ""
    significance: Literal["breaking", "refactor", "patch", "feature"] = "patch"


@dataclass
class FunctionChangeMeta:
    """Metadata for a function- or method-level change record."""

    agent: str = ""
    commit_hash: str = ""
    function_name: str = ""
    affected_callsites: str = ""   # space/comma separated paths


@dataclass
class BreakingChangeMeta:
    """Metadata for a breaking change record."""

    agent: str = ""
    commit_hash: str = ""
    what_broke: str = ""
    migration_note: str = ""


@dataclass
class RevertNoteMeta:
    """Metadata for a revert record."""

    agent: str = ""
    commit_hash: str = ""
    reverted_commit: str = ""
    reason: str = ""


def _file_paths_for_nodes(nodes: list[object]) -> list[str]:
    """Return unique file paths referenced by code_history nodes.

    ``source`` is authoritative. Legacy ``metadata.path`` is only used when a
    source marker is not available yet.
    """
    paths: set[str] = set()
    for node in nodes:
        source = getattr(node, "source", None)
        if isinstance(source, str) and "::" in source:
            paths.add(source.split("::", 1)[0])
            continue

        metadata = getattr(node, "metadata", {})
        if isinstance(metadata, dict):
            path = metadata.get("path")
            if isinstance(path, str) and path:
                paths.add(path)

    return sorted(paths)


def _run_git(project_root: Path, *args: str) -> str | None:
    """Run a git command and return trimmed stdout on success."""
    completed = subprocess.run(
        ["git", *args],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    stdout = completed.stdout.strip()
    return stdout or None


def _limit_lines(text: str | None, *, max_lines: int = 12) -> str | None:
    """Trim *text* to at most *max_lines* while preserving order."""
    if not text:
        return None
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    kept = lines[:max_lines]
    kept.append(f"... ({len(lines) - max_lines} more lines)")
    return "\n".join(kept)


def _gather_git_companion_context(request: RuntimeContextRequest) -> str | None:
    """Build git companion context for ``code_history``.

    The goal is to complement zhar memory with git's live view of the same
    files, not to duplicate full diff content already available elsewhere.
    """
    # %ZHAR:74c1%
    repo_root = _run_git(request.project_root, "rev-parse", "--show-toplevel")
    if repo_root is None:
        return None

    paths = _file_paths_for_nodes(request.nodes)
    if not paths:
        return None

    status_text = _limit_lines(
        _run_git(request.project_root, "status", "--short", "--", *paths),
        max_lines=10,
    )
    diff_stat = _limit_lines(
        _run_git(request.project_root, "diff", "--stat", "--", *paths),
        max_lines=10,
    )
    recent_log = _limit_lines(
        _run_git(request.project_root, "log", "--oneline", "-n", "5", "--", *paths),
        max_lines=5,
    )

    sections: list[str] = [
        "Complements code_history with git's live view for the same files.",
        f"Tracked files: {', '.join(paths)}",
    ]
    if status_text:
        sections.extend(["", "Working tree status:", status_text])
    if diff_stat:
        sections.extend(["", "Diff stat:", diff_stat])
    if recent_log:
        sections.extend(["", "Recent commits:", recent_log])

    return "\n".join(sections)


GROUP = GroupDef(
    name="code_history",
    export_limit=15,
    runtime_context_providers=[
        RuntimeContextProvider(
            name="git_companion",
            description="Summarise git status, diff stat, and recent commits for code_history files.",
            gather=_gather_git_companion_context,
        )
    ],
    node_types=[
        NodeTypeDef(
            name="file_change",
            meta_cls=FileChangeMeta,
            valid_statuses=["active", "stale", "archived"],
            default_status="active",
            current_statuses=["active"],
        ),
        NodeTypeDef(
            name="function_change",
            meta_cls=FunctionChangeMeta,
            valid_statuses=["active", "stale", "archived"],
            default_status="active",
            current_statuses=["active"],
        ),
        NodeTypeDef(
            name="breaking_change",
            meta_cls=BreakingChangeMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            current_statuses=["active"],
            memory_backed=True,
        ),
        NodeTypeDef(
            name="revert_note",
            meta_cls=RevertNoteMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            current_statuses=["active"],
        ),
    ],
)
