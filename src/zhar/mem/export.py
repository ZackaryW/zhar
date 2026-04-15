"""Context snapshot renderer — produces compact text for agent injection.

``export_text`` renders all (or filtered) active nodes grouped by group name.
``export_group`` renders a single group.

Output format (plain text, agent-readable)::

    # zhar memory — 4 nodes

    ## project_dna (2)
    [ffad] core_goal · Build zhar [tags: goal] agent=claude
    [f6ce] core_requirement · Use orjson [tags: perf] priority=high

    ## decision_trail (1)
    [c4b6] adr · Group-clustered storage [tags: arch]
      ## Status
      accepted

"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from zhar.mem_session.runtime import SessionRuntime, format_session_runtime_block

from zhar.mem.node import Node
from zhar.mem.query import Query
from zhar.mem.store import MemStore


def export_group(
    # %ZHAR:fdb3%
    store: MemStore,
    group: str,
    *,
    statuses: list[str] | None = None,
    tags: list[str] | None = None,
    relation_depth: int = 0,
    include_runtime_context: bool = False,
    project_root: Path | None = None,
) -> str:
    """Render all nodes in *group* as a text block.

    Returns ``""`` for unknown groups or groups with no matching nodes.
    """
    grouped_nodes = _collect_export_groups(
        store,
        target_groups=[group],
        statuses=statuses,
        tags=tags,
        relation_depth=relation_depth,
    )
    if not grouped_nodes:
        return ""

    blocks = [
        _render_group_block(
            store,
            actual_group,
            grouped_nodes[actual_group],
            include_runtime_context=include_runtime_context,
            project_root=project_root,
        )
        for actual_group in _ordered_group_names([group], grouped_nodes)
    ]
    return "\n\n".join(block for block in blocks if block)


def export_text(
    store: MemStore,
    *,
    groups: list[str] | None = None,
    statuses: list[str] | None = None,
    tags: list[str] | None = None,
    relation_depth: int = 0,
    include_runtime_context: bool = False,
    project_root: Path | None = None,
    session_runtime: SessionRuntime | None = None,
) -> str:
    """Render a full memory snapshot as plain text.

    Empty groups (no nodes matching the filter) are omitted.
    """
    target_groups = groups if groups is not None else [name for name in store.groups if name not in {"notes", "links"}]
    grouped_nodes = _collect_export_groups(
        store,
        target_groups=target_groups,
        statuses=statuses,
        tags=tags,
        relation_depth=relation_depth,
    )

    sections: list[str] = []
    total = 0
    for group in _ordered_group_names(target_groups, grouped_nodes):
        block = _render_group_block(
            store,
            group,
            grouped_nodes[group],
            include_runtime_context=include_runtime_context,
            project_root=project_root,
        )
        if not block:
            continue
        sections.append(block)
        total += len(grouped_nodes[group])

    if not sections:
        return "# zhar memory — 0 nodes\n"

    if include_runtime_context and session_runtime is not None:
        session_block = format_session_runtime_block(session_runtime)
        if session_block:
            sections.append(session_block)

    header = f"# zhar memory — {total} nodes\n"
    return header + "\n" + "\n\n".join(sections)


# ── helpers ───────────────────────────────────────────────────────────────────

def _sort_nodes(nodes: list[Node]) -> list[Node]:
    """Sort by node_type then created_at for stable output."""
    return sorted(nodes, key=lambda n: (n.node_type, n.created_at))


def expand_relation_nodes(
    store: MemStore,
    *,
    group: str,
    nodes: list[Node],
    statuses: list[str] | None,
    tags: list[str] | None,
    relation_depth: int,
) -> list[Node]:
    """Expand related nodes within the current export boundary.

    Relation-depth uses built-in ``links`` group edges that connect arbitrary
    node IDs via
      ``metadata.from_id`` and ``metadata.to_id``

    Missing or dangling link endpoints are ignored on read so traversal stays
    tolerant of deleted nodes and filtered boundaries.
    """
    if relation_depth <= 0:
        return nodes

    seed_ids = {node.id for node in nodes}
    if not seed_ids:
        return nodes

    eligible_nodes = _eligible_expansion_nodes(store, statuses=statuses, tags=tags)
    expanded_ids = _expand_related_ids(
        seed_ids=seed_ids,
        relation_depth=relation_depth,
        eligible_nodes=eligible_nodes,
        link_edges=_link_edge_candidates(store, statuses=statuses),
    )
    existing_ids = {node.id for node in nodes}
    expanded_nodes = [
        eligible_nodes[node_id] for node_id in expanded_ids
        if node_id not in existing_ids and node_id in eligible_nodes
    ]
    return nodes + expanded_nodes


def _collect_export_groups(
    store: MemStore,
    *,
    target_groups: list[str],
    statuses: list[str] | None,
    tags: list[str] | None,
    relation_depth: int,
) -> dict[str, list[Node]]:
    """Return exportable nodes grouped by actual group after expansion."""
    seed_nodes: list[Node] = []
    for group in target_groups:
        seed_nodes.extend(_group_seed_nodes(store, group, statuses=statuses, tags=tags))

    if not seed_nodes:
        return {}

    expanded_nodes = expand_relation_nodes(
        store,
        group=target_groups[0] if len(target_groups) == 1 else "*",
        nodes=seed_nodes,
        statuses=statuses,
        tags=tags,
        relation_depth=relation_depth,
    )
    grouped: dict[str, list[Node]] = {}
    for node in _sort_nodes(expanded_nodes):
        grouped.setdefault(node.group, []).append(node)

    for group, nodes in list(grouped.items()):
        grouped[group] = store.groups[group].limit_nodes_for_export(nodes)
        if not grouped[group]:
            grouped.pop(group)
    return grouped


def _group_seed_nodes(
    store: MemStore,
    group: str,
    *,
    statuses: list[str] | None,
    tags: list[str] | None,
) -> list[Node]:
    """Return seed nodes for one export group within the active boundary."""
    if group not in store.groups:
        return []
    nodes = store.query(Query(groups=[group], statuses=statuses, tags=tags))
    group_def = store.groups[group]
    if statuses is None:
        nodes = [node for node in nodes if group_def.is_current_node_for_export(node)]
    return nodes


def _render_group_block(
    store: MemStore,
    group: str,
    nodes: list[Node],
    *,
    include_runtime_context: bool,
    project_root: Path | None,
) -> str:
    """Render one already-collected group block for text export."""
    if not nodes:
        return ""

    lines: list[str] = [f"## {group} ({len(nodes)})"]
    for node in nodes:
        lines.append(_format_node_line(node))
        if node.content:
            for content_line in node.content.splitlines():
                lines.append(f"  {content_line}")

    if include_runtime_context:
        runtime_root = project_root if project_root is not None else store.project_root
        blocks = store.groups[group].gather_runtime_context(nodes=nodes, project_root=runtime_root)
        if blocks:
            lines.append("")
            lines.append("### Runtime context")
            for block in blocks:
                lines.append(f"#### {block.title}")
                for content_line in block.content.splitlines():
                    lines.append(content_line)
    return "\n".join(lines)


def _ordered_group_names(target_groups: list[str], grouped_nodes: dict[str, list[Node]]) -> list[str]:
    """Return deterministic group render order for export output."""
    ordered: list[str] = []
    for group in target_groups:
        if group in grouped_nodes and group not in ordered:
            ordered.append(group)
    for group in sorted(grouped_nodes):
        if group not in ordered:
            ordered.append(group)
    return ordered


def _eligible_expansion_nodes(
    store: MemStore,
    *,
    statuses: list[str] | None,
    tags: list[str] | None,
) -> dict[str, Node]:
    """Return nodes eligible to appear as expanded relation results."""
    candidate_groups = [name for name in store.groups if name not in {"notes", "links"}]
    nodes = store.query(Query(groups=candidate_groups, statuses=statuses, tags=tags))
    eligible: dict[str, Node] = {}
    for node in nodes:
        group_def = store.groups[node.group]
        if statuses is None and not group_def.is_current_node_for_export(node):
            continue
        eligible[node.id] = node
    return eligible


def _expand_related_ids(
    *,
    seed_ids: set[str],
    relation_depth: int,
    eligible_nodes: dict[str, Node],
    link_edges: list[Node],
) -> set[str]:
    """Return related node IDs reachable within the active traversal boundary."""
    visited = {node_id for node_id in seed_ids if node_id in eligible_nodes}
    frontier = set(visited)

    for _ in range(relation_depth):
        if not frontier:
            break
        next_frontier: set[str] = set()
        for node_id in frontier:
            next_frontier |= _link_neighbors(link_edges, node_id)
        next_frontier = {
            node_id for node_id in next_frontier
            if node_id in eligible_nodes and node_id not in visited
        }
        visited |= next_frontier
        frontier = next_frontier

    return visited


def _link_edge_candidates(
    store: MemStore,
    *,
    statuses: list[str] | None,
) -> list[Node]:
    """Return active built-in link-edge nodes."""
    nodes = store.query(Query(groups=["links"], statuses=statuses))
    group_def = store.groups["links"]
    if statuses is None:
        nodes = [node for node in nodes if group_def.is_current_node_for_export(node)]
    return nodes


def _link_neighbors(link_edges: list[Node], node_id: str) -> set[str]:
    """Return neighboring node IDs connected by optional link edges."""
    neighbors: set[str] = set()
    for edge in link_edges:
        from_id = str(edge.metadata.get("from_id", "")).strip()
        to_id = str(edge.metadata.get("to_id", "")).strip()
        if not from_id or not to_id:
            continue
        if from_id == node_id:
            neighbors.add(to_id)
        if to_id == node_id:
            neighbors.add(from_id)
    return neighbors


def _format_node_line(node: Node) -> str:
    """Render one node as a compact single-line export entry."""
    parts: list[str] = [f"[{node.id}] {node.node_type} · {node.summary}"]
    if node.tags:
        parts.append(f"[tags: {', '.join(node.tags)}]")
    if node.status != "active":
        parts.append(f"status={node.status}")
    if node.source:
        parts.append(f"source={node.source}")
    if node.metadata:
        for k, v in _visible_metadata(node):
            parts.append(f"{k}={v}")
    return " ".join(parts)


def _visible_metadata(node: Node) -> list[tuple[str, Any]]:
    """Return metadata items that should appear in text exports.

    ``code_history/file_change`` treats ``source`` as authoritative once set,
    so redundant legacy ``path`` metadata is hidden from agent-facing output.
    """
    items = list(node.metadata.items())
    if node.group == "code_history" and node.node_type == "file_change" and node.source:
        return [(key, value) for key, value in items if key != "path"]
    return items
