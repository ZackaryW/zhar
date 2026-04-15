"""Structured serializers for zhar CLI output surfaces."""

from __future__ import annotations

from typing import Any

import orjson

from zhar.mem.node import Node
from zhar.mem_session.model import SessionNodeState
from zhar.mem_session.runtime import SessionRuntime
from zhar.mem_session.store import load_session
from zhar.utils.times import format_dt


def node_to_payload(node: Node) -> dict[str, Any]:
    """Return a JSON-safe dictionary for one memory node."""
    return {
        "id": node.id,
        "group": node.group,
        "node_type": node.node_type,
        "status": node.status,
        "summary": node.summary,
        "tags": node.tags,
        "source": node.source,
        "content": node.content,
        "metadata": node.metadata,
        "custom": node.custom,
        "created_at": format_dt(node.created_at),
        "updated_at": format_dt(node.updated_at),
        "expires_at": format_dt(node.expires_at) if node.expires_at is not None else None,
    }


def show_to_payload(node: Node, related_nodes: list[Node]) -> dict[str, Any]:
    """Return a JSON-safe payload for the show command."""
    return {
        "node": node_to_payload(node),
        "related_nodes": [node_to_payload(related) for related in related_nodes],
    }


def query_to_payload(
    nodes: list[Node],
    *,
    note_map: dict[str, list[Node]] | None = None,
) -> dict[str, Any]:
    """Return a JSON-safe payload for query output."""
    serialized_nodes: list[dict[str, Any]] = []
    for node in nodes:
        payload = node_to_payload(node)
        payload["notes"] = [
            node_to_payload(note)
            for note in (note_map or {}).get(node.id, [])
        ]
        serialized_nodes.append(payload)
    return {
        "count": len(serialized_nodes),
        "nodes": serialized_nodes,
    }


def status_to_payload(stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return a JSON-safe payload for status output."""
    return {
        "total_nodes": sum(value["total"] for value in stats.values()),
        "groups": stats,
    }


def session_current_to_payload(
    *,
    session_id: str,
    enabled: bool,
    project_root: str,
    session_dir: str,
    shown_nodes: int,
    suspicious_nodes: int,
    challenge_enabled: bool,
    challenge_agent: str | None,
) -> dict[str, Any]:
    """Return a JSON-safe payload for the session current command."""
    payload = {
        "session_id": session_id,
        "enabled": enabled,
        "project_root": project_root,
        "session_dir": session_dir,
        "shown_nodes": shown_nodes,
        "suspicious_nodes": suspicious_nodes,
        "challenge_enabled": challenge_enabled,
    }
    if challenge_agent is not None:
        payload["challenge_agent"] = challenge_agent
    return payload


def runtime_blocks_to_payload(blocks: list[Any]) -> list[dict[str, str]]:
    """Return JSON-safe payloads for runtime context blocks."""
    return [
        {
            "title": block.title,
            "content": block.content,
        }
        for block in blocks
    ]


def session_node_state_to_payload(node_id: str, state: SessionNodeState) -> dict[str, Any]:
    """Return a JSON-safe payload for one transient session node state."""
    payload = {"id": node_id}
    payload.update(state.to_dict())
    return payload


def session_runtime_to_payload(runtime: SessionRuntime) -> dict[str, Any] | None:
    """Return structured export payload for the active transient session."""
    if not runtime.enabled:
        return None
    session = load_session(runtime.session_id, base_dir=runtime.session_dir)
    if session is None or not session.nodes:
        return None

    suspicious_ids = sorted(
        node_id for node_id, state in session.nodes.items()
        if state.status == "suspicious"
    )
    payload = {
        "session_id": runtime.session_id,
        "shown_nodes": len(session.nodes),
        "suspicious_nodes": len(suspicious_ids),
        "challenge_enabled": runtime.challenge_enabled,
        "nodes": [
            session_node_state_to_payload(node_id, state)
            for node_id, state in sorted(session.nodes.items())
        ],
    }
    if runtime.challenge_enabled and runtime.challenge_agent is not None:
        payload["challenge_agent"] = runtime.challenge_agent
    return payload


def render_json(payload: dict[str, Any] | list[dict[str, Any]]) -> str:
    """Return a stable pretty-printed JSON string for *payload*."""
    return orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode("utf-8")