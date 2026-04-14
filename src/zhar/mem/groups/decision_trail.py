"""Built-in group: decision_trail — architectural decisions and research.

Node types
----------
adr               Architecture Decision Record.
decision          A concrete design or implementation decision.
lesson_learned    Something discovered that should influence future work.
research_finding  Result of a spike or research task.
"""
from dataclasses import dataclass
from typing import Literal

from zhar.mem.group import GroupDef, NodeTypeDef


@dataclass
class AdrMeta:
    agent: str = ""


@dataclass
class DecisionMeta:
    agent: str = ""
    commit_hash: str = ""
    alternatives_considered: str = ""
    tradeoffs: str = ""


@dataclass
class LessonLearnedMeta:
    agent: str = ""
    trigger_event: str = ""


@dataclass
class ResearchFindingMeta:
    agent: str = ""
    outcome: Literal["adopted", "rejected", "deferred"] = "deferred"
    source_ref: str = ""


GROUP = GroupDef(
    name="decision_trail",
    node_types=[
        NodeTypeDef(
            name="adr",
            meta_cls=AdrMeta,
            valid_statuses=["proposed", "accepted", "superseded"],
            default_status="proposed",
            current_statuses=["accepted"],
            memory_backed=True,
        ),
        NodeTypeDef(
            name="decision",
            meta_cls=DecisionMeta,
            valid_statuses=["active", "superseded", "archived"],
            default_status="active",
            current_statuses=["active"],
        ),
        NodeTypeDef(
            name="lesson_learned",
            meta_cls=LessonLearnedMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            current_statuses=["active"],
            memory_backed=True,
        ),
        NodeTypeDef(
            name="research_finding",
            meta_cls=ResearchFindingMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            current_statuses=["active"],
            memory_backed=True,
        ),
    ],
)
