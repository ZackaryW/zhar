"""Built-in group: problem_tracking — live issues, blockers, and bugs.

Node types
----------
known_issue    An active bug, design flaw, or tech-debt item.
blocked        A task or decision that is waiting on something.
"""
from dataclasses import dataclass
from typing import Literal

from zhar.mem.group import GroupDef, NodeTypeDef


@dataclass
class KnownIssueMeta:
    agent: str = ""
    severity: Literal["low", "med", "high", "critical"] = "med"
    issue_type: Literal["bug", "debt", "design"] = "bug"
    commit_hash: str = ""


@dataclass
class BlockedMeta:
    agent: str = ""
    blocker_ref: str = ""   # node ID or free-form description


GROUP = GroupDef(
    name="problem_tracking",
    node_types=[
        NodeTypeDef(
            name="known_issue",
            meta_cls=KnownIssueMeta,
            valid_statuses=["active", "resolved", "archived"],
            default_status="active",
            current_statuses=["active"],
            memory_backed=True,
        ),
        NodeTypeDef(
            name="blocked",
            meta_cls=BlockedMeta,
            valid_statuses=["active", "resolved"],
            default_status="active",
            current_statuses=["active"],
        ),
    ],
)
