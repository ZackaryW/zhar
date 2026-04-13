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

from zhar.mem.node import Node
from zhar.mem.query import Query
from zhar.mem.store import MemStore


def export_group(
    store: MemStore,
    group: str,
    *,
    statuses: list[str] | None = None,
) -> str:
    """Render all nodes in *group* as a text block.

    Returns ``""`` for unknown groups or groups with no matching nodes.
    """
    if group not in store.groups:
        return ""

    nodes = store.query(Query(
        groups=[group],
        statuses=statuses,
    ))
    if not nodes:
        return ""

    lines: list[str] = [f"## {group} ({len(nodes)})"]
    for node in _sort_nodes(nodes):
        lines.append(_format_node_line(node))
        if node.content:
            for content_line in node.content.splitlines():
                lines.append(f"  {content_line}")
    return "\n".join(lines)


def export_text(
    store: MemStore,
    *,
    groups: list[str] | None = None,
    statuses: list[str] | None = None,
) -> str:
    """Render a full memory snapshot as plain text.

    Empty groups (no nodes matching the filter) are omitted.
    """
    target_groups = groups if groups is not None else list(store.groups)

    sections: list[str] = []
    total = 0
    for group in target_groups:
        block = export_group(store, group, statuses=statuses)
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

    header = f"# zhar memory — {total} nodes\n"
    return header + "\n" + "\n\n".join(sections)


# ── helpers ───────────────────────────────────────────────────────────────────

def _sort_nodes(nodes: list[Node]) -> list[Node]:
    """Sort by node_type then created_at for stable output."""
    return sorted(nodes, key=lambda n: (n.node_type, n.created_at))


def _format_node_line(node: Node) -> str:
    parts: list[str] = [f"[{node.id}] {node.node_type} · {node.summary}"]
    if node.tags:
        parts.append(f"[tags: {', '.join(node.tags)}]")
    if node.status != "active":
        parts.append(f"status={node.status}")
    if node.source:
        parts.append(f"source={node.source}")
    if node.metadata:
        for k, v in node.metadata.items():
            parts.append(f"{k}={v}")
    return " ".join(parts)
