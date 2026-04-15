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
    if group not in store.groups:
        return ""

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
        return ""

    nodes = group_def.limit_nodes_for_export(_sort_nodes(nodes))
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
        blocks = group_def.gather_runtime_context(
            nodes=nodes,
            project_root=runtime_root,
        )
        if blocks:
            lines.append("")
            lines.append("### Runtime context")
            for block in blocks:
                lines.append(f"#### {block.title}")
                for content_line in block.content.splitlines():
                    lines.append(content_line)
    return "\n".join(lines)


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
    target_groups = groups if groups is not None else [name for name in store.groups if name != "notes"]

    sections: list[str] = []
    total = 0
    for group in target_groups:
        block = export_group(
            store,
            group,
            statuses=statuses,
            tags=tags,
            relation_depth=relation_depth,
            include_runtime_context=include_runtime_context,
            project_root=project_root,
        )
        if block:
            sections.append(block)
            # Count nodes from first line "## group (N)"
            first_line = block.splitlines()[0]
            try:
                total += int(first_line.rsplit("(", 1)[1].rstrip(")"))
            except (IndexError, ValueError):
                pass

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
    """Expand component relationship nodes within the current export boundary.

    Expansion is intentionally limited to ``architecture_context/component_rel``
    nodes. Candidate relation nodes are filtered through the same tag and status
    selectors as the seed set so namespace and lifecycle boundaries remain hard.
    """
    if relation_depth <= 0 or group != "architecture_context":
        return nodes

    seed_ids = {node.id for node in nodes if node.node_type == "component_rel"}
    if not seed_ids:
        return nodes

    relation_candidates = _relation_candidates(
        store,
        statuses=statuses,
        tags=tags,
    )
    if not relation_candidates:
        return nodes

    expanded_ids = _expand_relation_ids(relation_candidates, seed_ids, relation_depth)
    existing_ids = {node.id for node in nodes}
    expanded_nodes = [
        node for node in relation_candidates
        if node.id in expanded_ids and node.id not in existing_ids
    ]
    return nodes + expanded_nodes


def _relation_candidates(
    store: MemStore,
    *,
    statuses: list[str] | None,
    tags: list[str] | None,
) -> list[Node]:
    """Return relation nodes eligible for export expansion.

    The returned set already honors the requested status and tag filters, plus
    the group's default current-boundary semantics when no explicit statuses are
    supplied.
    """
    nodes = store.query(Query(
        groups=["architecture_context"],
        node_types=["component_rel"],
        statuses=statuses,
        tags=tags,
    ))
    if statuses is not None:
        return nodes

    group_def = store.groups["architecture_context"]
    return [node for node in nodes if group_def.is_current_node_for_export(node)]


def _expand_relation_ids(
    relation_nodes: list[Node],
    seed_ids: set[str],
    relation_depth: int,
) -> set[str]:
    """Return relation node IDs reachable from *seed_ids* within *relation_depth*.

    Two ``component_rel`` nodes are adjacent when they share at least one
    component endpoint across ``from_component`` and ``to_component`` metadata.
    """
    relation_by_id = {node.id: node for node in relation_nodes}
    visited = {node_id for node_id in seed_ids if node_id in relation_by_id}
    frontier = set(visited)

    for _ in range(relation_depth):
        if not frontier:
            break
        frontier_components = set()
        for node_id in frontier:
            frontier_components.update(_relation_components(relation_by_id[node_id]))

        next_frontier: set[str] = set()
        for node in relation_nodes:
            if node.id in visited:
                continue
            if frontier_components & _relation_components(node):
                next_frontier.add(node.id)

        visited |= next_frontier
        frontier = next_frontier

    return visited


def _relation_components(node: Node) -> set[str]:
    """Return the normalized endpoint component names referenced by *node*."""
    components: set[str] = set()
    for key in ("from_component", "to_component"):
        value = str(node.metadata.get(key, "")).strip()
        if value:
            components.add(value)
    return components


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
