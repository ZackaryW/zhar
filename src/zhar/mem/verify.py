"""Completeness and consistency checks for the memory store.

Checks
------
MISSING_SINGLETON   A singleton node type has no active node.
MISSING_CONTENT     A memory-backed node type has nodes with no content body.
BROKEN_SOURCE       A node's source field references a file that does not exist.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

from zhar.mem.query import Query
from zhar.mem.store import MemStore


class Severity(str, enum.Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass(frozen=True)
class VerifyIssue:
    severity: Severity
    code: str
    message: str


def run_verify(
    # %ZHAR:2b1c%
    store: MemStore,
    *,
    project_root: Path | None = None,
) -> list[VerifyIssue]:
    """Run all checks and return a list of VerifyIssue objects.

    Parameters
    ----------
    store:
        The MemStore to inspect.
    project_root:
        When provided, source file paths are resolved relative to this
        directory for the BROKEN_SOURCE check.  When None, that check
        is skipped.
    """
    issues: list[VerifyIssue] = []

    issues.extend(_check_missing_singletons(store))
    issues.extend(_check_missing_content(store))
    if project_root is not None:
        issues.extend(_check_broken_sources(store, project_root))

    return issues


# ── individual checks ─────────────────────────────────────────────────────────

def _check_missing_singletons(store: MemStore) -> list[VerifyIssue]:
    issues: list[VerifyIssue] = []
    for group_name, group_def in store.groups.items():
        for type_def in group_def.node_types:
            if not type_def.singleton:
                continue
            existing = store.index.singleton(group_name, type_def.name)
            if existing is None:
                issues.append(VerifyIssue(
                    severity=Severity.WARN,
                    code="MISSING_SINGLETON",
                    message=(
                        f"Group '{group_name}': no active '{type_def.name}' node. "
                        f"Add one with: zhar add {group_name} {type_def.name} \"...\""
                    ),
                ))
    return issues


def _check_missing_content(store: MemStore) -> list[VerifyIssue]:
    issues: list[VerifyIssue] = []
    for node in store.query(Query()):
        group_def = store.groups.get(node.group)
        if group_def is None:
            continue
        try:
            type_def = group_def.get_type(node.node_type)
        except KeyError:
            continue
        if type_def.memory_backed and node.content is None:
            issues.append(VerifyIssue(
                severity=Severity.INFO,
                code="MISSING_CONTENT",
                message=(
                    f"Node [{node.id}] '{node.summary}' ({node.group}/{node.node_type}) "
                    f"is memory-backed but has no content body. "
                    f"Add it with: zhar note {node.id} \"...\""
                ),
            ))
    return issues


def _check_broken_sources(
    store: MemStore, project_root: Path
) -> list[VerifyIssue]:
    issues: list[VerifyIssue] = []
    for node in store.query(Query()):
        if not node.source:
            continue
        # Source format: path::line::%ZHAR:id%  or just a bare path
        file_part = node.source.split("::")[0]
        resolved = project_root / file_part
        if not resolved.exists():
            issues.append(VerifyIssue(
                severity=Severity.WARN,
                code="BROKEN_SOURCE",
                message=(
                    f"Node [{node.id}] '{node.summary}': source file "
                    f"'{file_part}' does not exist."
                ),
            ))
    return issues
