"""Import zmem graph.json state into zhar memory."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson

from zhar.mem.node import make_node
from zhar.mem.store import MemStore
from zhar.utils.times import parse_dt


@dataclass(frozen=True)
class ZmemMigrationReport:
    """Summary of one zmem-to-zhar migration run."""

    migrated_nodes: int
    created_notes: int
    preserved_ids: int


def migrate_zmem_json(store: MemStore, source_path: Path) -> ZmemMigrationReport:
    """Import the JSON surface of a zmem instance into ``store``.

    Only ``graph.json`` is read. Markdown memory files and inline source content
    are intentionally not parsed during migration.
    """
    graph_path = source_path / "graph.json" if source_path.is_dir() else source_path
    payload = orjson.loads(graph_path.read_bytes())

    preserved_ids = 0
    migrated_nodes = 0
    created_notes = 0
    task_state_host_id: str | None = None

    for record in payload.get("nodes", []):
        plan = _plan_record(record)
        if plan is None:
            continue

        preferred_id = record["id"] if plan.allow_legacy_id else None
        allocated_id = store.allocate_id(preferred_id, length=5 if preferred_id is None else len(preferred_id))
        if preferred_id is not None and allocated_id == preferred_id:
            preserved_ids += 1

        if plan.host_kind == "task_state":
            if task_state_host_id is None:
                task_state_host_id = _create_task_state_host(store)
                migrated_nodes += 1
            _create_note(store, task_state_host_id, record)
            created_notes += 1
            continue

        node = make_node(
            node_id=allocated_id,
            group=plan.group,
            node_type=plan.node_type,
            summary=_summary_for_record(record),
            status=_status_for_record(store, plan.group, plan.node_type, str(record.get("status", "active"))),
            tags=[str(tag) for tag in record.get("tags", [])],
            created_at=parse_dt(record["created_at"]),
            updated_at=parse_dt(record["updated_at"]),
            expires_at=parse_dt(record["expires_at"]) if record.get("expires_at") else None,
            metadata=_mapped_metadata(store, plan.group, plan.node_type, record),
            content=_content_for_record(store, plan.group, plan.node_type, record),
            custom={"migration_source": "zmem-json", "zmem_type": str(record.get("type", ""))},
        )
        store.save(node)
        migrated_nodes += 1

        _create_note(store, node.id, record)
        created_notes += 1

    return ZmemMigrationReport(
        migrated_nodes=migrated_nodes,
        created_notes=created_notes,
        preserved_ids=preserved_ids,
    )


@dataclass(frozen=True)
class _MigrationPlan:
    """Resolved zmem-to-zhar target plan for a single source node."""

    group: str
    node_type: str
    allow_legacy_id: bool = True
    host_kind: str | None = None


def _plan_record(record: dict[str, Any]) -> _MigrationPlan | None:
    """Return the zhar destination for one zmem node record."""
    node_type = str(record.get("type", ""))
    direct_map = {
        "core_goal": ("project_dna", "core_goal"),
        "core_requirement": ("project_dna", "core_requirement"),
        "product_context": ("project_dna", "product_context"),
        "stakeholder": ("project_dna", "stakeholder"),
        "known_issue": ("problem_tracking", "known_issue"),
        "blocked": ("problem_tracking", "blocked"),
        "adr": ("decision_trail", "adr"),
        "decision": ("decision_trail", "decision"),
        "lesson_learned": ("decision_trail", "lesson_learned"),
        "research_finding": ("decision_trail", "research_finding"),
        "architecture": ("architecture_context", "architecture"),
        "design_pattern": ("architecture_context", "design_pattern"),
        "component_rel": ("architecture_context", "component_rel"),
        "tech_stack": ("architecture_context", "tech_stack"),
        "tech_setup": ("architecture_context", "tech_setup"),
        "tech_constraint": ("architecture_context", "tech_constraint"),
        "env_config": ("architecture_context", "env_config"),
        "external_dep": ("architecture_context", "external_dep"),
        "file_change": ("code_history", "file_change"),
        "function_change": ("code_history", "function_change"),
        "breaking_change": ("code_history", "breaking_change"),
        "revert_note": ("code_history", "revert_note"),
    }
    if node_type in direct_map:
        group, mapped_type = direct_map[node_type]
        return _MigrationPlan(group=group, node_type=mapped_type)
    if node_type in {"current_focus", "currently_working", "in_progress", "next_step", "completed", "abandoned"}:
        return _MigrationPlan(group="project_dna", node_type="product_context", allow_legacy_id=False, host_kind="task_state")
    return None


def _summary_for_record(record: dict[str, Any]) -> str:
    """Return a deterministic zhar summary for one zmem record."""
    custom = record.get("custom", {})
    summary = custom.get("summary") if isinstance(custom, dict) else None
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return f"Migrated zmem {record.get('type', 'node')} {record.get('id', 'unknown')}"


def _mapped_metadata(store: MemStore, group: str, node_type: str, record: dict[str, Any]) -> dict[str, Any]:
    """Return zhar-valid metadata copied from a zmem record when fields overlap."""
    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    fields = {field.name for field in dataclasses.fields(store.groups[group].get_type(node_type).meta_cls)}
    mapped: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in fields and isinstance(value, str):
            mapped[key] = value
    if "agent" in fields and "agent" not in mapped:
        mapped["agent"] = "migration"
    return mapped


def _content_for_record(store: MemStore, group: str, node_type: str, record: dict[str, Any]) -> str | None:
    """Return generated markdown content for memory-backed zhar targets."""
    if not store.groups[group].get_type(node_type).memory_backed:
        return None
    lines = [
        "## Imported From zmem JSON",
        "",
        f"- original_id: {record.get('id', '')}",
        f"- original_type: {record.get('type', '')}",
        f"- original_status: {record.get('status', '')}",
    ]
    source = str(record.get("source", "")).strip()
    if source:
        lines.append(f"- original_source: {source}")
    return "\n".join(lines)


def _status_for_record(store: MemStore, group: str, node_type: str, status: str) -> str:
    """Map a zmem status to a valid zhar status for the destination type."""
    valid_statuses = store.groups[group].get_type(node_type).valid_statuses
    return status if status in valid_statuses else store.groups[group].default_status(node_type)


def _create_task_state_host(store: MemStore) -> str:
    """Create and return the synthetic base node used for imported task-state notes."""
    node = make_node(
        node_id=store.allocate_id(),
        group="project_dna",
        node_type="product_context",
        summary="Migrated zmem task-state context",
        metadata={"agent": "migration", "audience": "agents"},
        content="## Imported From zmem JSON\n\nSynthetic host for task-state notes.",
    )
    store.save(node)
    return node.id


def _create_note(store: MemStore, target_id: str, record: dict[str, Any]) -> None:
    """Create one supplemental note that preserves the original zmem JSON record."""
    pretty_json = orjson.dumps(record, option=orjson.OPT_INDENT_2).decode("utf-8")
    node = make_node(
        node_id=store.allocate_id(),
        group="notes",
        node_type="note",
        summary=f"Imported zmem note for {target_id}",
        tags=["migration", "zmem", str(record.get("type", ""))],
        metadata={"agent": "migration", "target_ids": target_id},
        content=f"## zmem JSON record\n\n```json\n{pretty_json}\n```",
        custom={"migration_source": "zmem-json"},
    )
    store.save(node)