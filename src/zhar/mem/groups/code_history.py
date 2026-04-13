"""Built-in group: code_history — code-level change records.

Node types
----------
file_change       A significant change to a file.
function_change   A change to a specific function or method.
breaking_change   A change that breaks existing callers or contracts.
revert_note       A record of a revert and why it was made.
"""
from dataclasses import dataclass
from typing import Literal

from zhar.mem.group import GroupDef, NodeTypeDef


@dataclass
class FileChangeMeta:
    agent: str = ""
    commit_hash: str = ""
    path: str = ""
    significance: Literal["breaking", "refactor", "patch", "feature"] = "patch"


@dataclass
class FunctionChangeMeta:
    agent: str = ""
    commit_hash: str = ""
    function_name: str = ""
    affected_callsites: str = ""   # space/comma separated paths


@dataclass
class BreakingChangeMeta:
    agent: str = ""
    commit_hash: str = ""
    what_broke: str = ""
    migration_note: str = ""


@dataclass
class RevertNoteMeta:
    agent: str = ""
    commit_hash: str = ""
    reverted_commit: str = ""
    reason: str = ""


GROUP = GroupDef(
    name="code_history",
    node_types=[
        NodeTypeDef(
            name="file_change",
            meta_cls=FileChangeMeta,
            valid_statuses=["active", "stale", "archived"],
            default_status="active",
        ),
        NodeTypeDef(
            name="function_change",
            meta_cls=FunctionChangeMeta,
            valid_statuses=["active", "stale", "archived"],
            default_status="active",
        ),
        NodeTypeDef(
            name="breaking_change",
            meta_cls=BreakingChangeMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            memory_backed=True,
        ),
        NodeTypeDef(
            name="revert_note",
            meta_cls=RevertNoteMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
        ),
    ],
)
