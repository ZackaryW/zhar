"""Built-in group: architecture_context - architecture, design, and tech context.

Node types
----------
architecture     A high-level architecture snapshot or boundary description.
design_pattern   A documented design pattern used in the project.
component_rel    A descriptive relationship record between two components.
tech_stack       A technology stack record for a component or area.
tech_setup       A setup recipe or operational context note.
tech_constraint  A durable technical constraint.
env_config       An environment-specific configuration record.
external_dep     A dependency on an external service or API.
"""
from dataclasses import dataclass
from typing import Literal

from zhar.mem.group import GroupDef, NodeTypeDef


@dataclass
class ArchitectureMeta:
    """Metadata for an architecture snapshot."""

    agent: str = ""
    diagram_ref: str = ""


@dataclass
class DesignPatternMeta:
    """Metadata for a documented design pattern record."""

    agent: str = ""


@dataclass
class ComponentRelMeta:
    """Metadata for a descriptive component-to-component relationship record."""

    agent: str = ""
    from_component: str = ""
    to_component: str = ""
    rel_type: str = ""
    contract: str = ""


@dataclass
class TechStackMeta:
    """Metadata for a technology stack record."""

    agent: str = ""
    language: str = ""
    framework: str = ""
    version: str = ""


@dataclass
class TechSetupMeta:
    """Metadata for a setup or operational context note."""

    agent: str = ""


@dataclass
class TechConstraintMeta:
    """Metadata for a durable technical constraint."""

    agent: str = ""
    category: Literal["perf", "security", "compliance", "budget"] = "perf"


@dataclass
class EnvConfigMeta:
    """Metadata for an environment-specific configuration record."""

    agent: str = ""
    env: Literal["dev", "staging", "prod"] = "dev"


@dataclass
class ExternalDepMeta:
    """Metadata for an external dependency record."""

    agent: str = ""
    service_name: str = ""
    api_version: str = ""
    failure_modes: str = ""


GROUP = GroupDef(
    name="architecture_context",
    node_types=[
        NodeTypeDef(
            name="architecture",
            meta_cls=ArchitectureMeta,
            valid_statuses=["active", "stale", "archived"],
            default_status="active",
            current_statuses=["active"],
            memory_backed=True,
        ),
        NodeTypeDef(
            name="design_pattern",
            meta_cls=DesignPatternMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            current_statuses=["active"],
            memory_backed=True,
        ),
        NodeTypeDef(
            name="component_rel",
            meta_cls=ComponentRelMeta,
            valid_statuses=["active", "deprecated", "archived"],
            default_status="active",
            current_statuses=["active"],
        ),
        NodeTypeDef(
            name="tech_stack",
            meta_cls=TechStackMeta,
            valid_statuses=["active", "stale", "archived"],
            default_status="active",
            current_statuses=["active"],
        ),
        NodeTypeDef(
            name="tech_setup",
            meta_cls=TechSetupMeta,
            valid_statuses=["active", "stale", "archived"],
            default_status="active",
            current_statuses=["active"],
            memory_backed=True,
        ),
        NodeTypeDef(
            name="tech_constraint",
            meta_cls=TechConstraintMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            current_statuses=["active"],
            memory_backed=True,
        ),
        NodeTypeDef(
            name="env_config",
            meta_cls=EnvConfigMeta,
            valid_statuses=["active", "stale", "archived"],
            default_status="active",
            current_statuses=["active"],
        ),
        NodeTypeDef(
            name="external_dep",
            meta_cls=ExternalDepMeta,
            valid_statuses=["active", "deprecated", "archived"],
            default_status="active",
            current_statuses=["active"],
        ),
    ],
)