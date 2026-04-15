"""Structured export payload builders for JSON CLI surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from zhar.cli.serializers import node_to_payload, runtime_blocks_to_payload, session_runtime_to_payload
from zhar.mem.export import expand_relation_nodes
from zhar.mem.query import Query
from zhar.mem.store import MemStore
from zhar.mem_session.runtime import SessionRuntime


def export_group_payload(
    store: MemStore,
    group: str,
    *,
    statuses: list[str] | None = None,
    tags: list[str] | None = None,
    relation_depth: int = 0,
    include_runtime_context: bool = False,
    project_root: Path | None = None,
) -> dict[str, Any] | None:
    """Return structured export data for one group or ``None`` when empty."""
    if group not in store.groups:
        return None

    nodes = store.query(Query(
        groups=[group],
        statuses=statuses,
        tags=tags,
    ))
    group_def = store.groups[group]
    if statuses is None:
        nodes = [node for node in nodes if group_def.is_current_node_for_export(node)]
    nodes = expand_relation_nodes(
        store,
        group=group,
        nodes=nodes,
        statuses=statuses,
        tags=tags,
        relation_depth=relation_depth,
    )
    if not nodes:
        return None

    nodes = group_def.limit_nodes_for_export(sorted(nodes, key=lambda node: (node.node_type, node.created_at)))
    if not nodes:
        return None

    payload: dict[str, Any] = {
        "count": len(nodes),
        "nodes": [node_to_payload(node) for node in nodes],
    }
    if include_runtime_context:
        runtime_root = project_root if project_root is not None else store.project_root
        blocks = group_def.gather_runtime_context(nodes=nodes, project_root=runtime_root)
        if blocks:
            payload["runtime_context"] = runtime_blocks_to_payload(blocks)
    return payload


def export_payload(
    store: MemStore,
    *,
    groups: list[str] | None = None,
    statuses: list[str] | None = None,
    tags: list[str] | None = None,
    relation_depth: int = 0,
    include_runtime_context: bool = False,
    project_root: Path | None = None,
    session_runtime: SessionRuntime | None = None,
) -> dict[str, Any]:
    """Return structured export data for the requested memory snapshot."""
    target_groups = groups if groups is not None else [name for name in store.groups if name != "notes"]

    group_payloads: dict[str, Any] = {}
    total_nodes = 0
    runtime_group_payloads: dict[str, Any] = {}
    for group in target_groups:
        payload = export_group_payload(
            store,
            group,
            statuses=statuses,
            tags=tags,
            relation_depth=relation_depth,
            include_runtime_context=include_runtime_context,
            project_root=project_root,
        )
        if payload is None:
            continue
        group_payloads[group] = {
            "count": payload["count"],
            "nodes": payload["nodes"],
        }
        total_nodes += int(payload["count"])
        if include_runtime_context and "runtime_context" in payload:
            runtime_group_payloads[group] = payload["runtime_context"]

    result: dict[str, Any] = {
        "total_nodes": total_nodes,
        "groups": group_payloads,
    }
    if include_runtime_context:
        runtime_payload: dict[str, Any] = {}
        if runtime_group_payloads:
            runtime_payload["groups"] = runtime_group_payloads
        if session_runtime is not None:
            session_payload = session_runtime_to_payload(session_runtime)
            if session_payload is not None:
                runtime_payload["session"] = session_payload
        if runtime_payload:
            result["runtime_context"] = runtime_payload
    return result