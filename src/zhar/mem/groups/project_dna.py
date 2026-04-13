"""Built-in group: project_dna — stable, high-level project context.

Node types
----------
core_goal          Singleton. The primary mission of the project.
core_requirement   A hard requirement (functional or non-functional).
product_context    Audience, positioning, or market context.
stakeholder        A person or system with authority over decisions.
"""
from dataclasses import dataclass
from typing import Literal

from zhar.mem.group import GroupDef, NodeTypeDef


@dataclass
class CoreGoalMeta:
    agent: str = ""


@dataclass
class CoreRequirementMeta:
    agent: str = ""
    priority: Literal["low", "med", "high"] = "med"


@dataclass
class ProductContextMeta:
    agent: str = ""
    audience: str = ""


@dataclass
class StakeholderMeta:
    agent: str = ""
    role: str = ""
    authority_scope: str = ""


GROUP = GroupDef(
    name="project_dna",
    node_types=[
        NodeTypeDef(
            name="core_goal",
            meta_cls=CoreGoalMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            singleton=True,
        ),
        NodeTypeDef(
            name="core_requirement",
            meta_cls=CoreRequirementMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            memory_backed=True,
        ),
        NodeTypeDef(
            name="product_context",
            meta_cls=ProductContextMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            memory_backed=True,
        ),
        NodeTypeDef(
            name="stakeholder",
            meta_cls=StakeholderMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
        ),
    ],
)
