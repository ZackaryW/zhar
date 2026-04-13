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

from zhar.mem.node import Node
from zhar.mem.query import Query
from zhar.mem.store import MemStore


def export_group(
    # %ZHAR:fdb3%
    store: MemStore,
    group: str,
    *,
    statuses: list[str] | None = None,
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
    ))
    if not nodes:
        return ""

    lines: list[str] = [f"## {group} ({len(nodes)})"]
    for node in _sort_nodes(nodes):
        lines.append(_format_node_line(node))
        if node.content:
            for content_line in node.content.splitlines():
                lines.append(f"  {content_line}")

    if include_runtime_context:
        runtime_root = project_root if project_root is not None else store.project_root
        blocks = store.groups[group].gather_runtime_context(
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
    include_runtime_context: bool = False,
    project_root: Path | None = None,
) -> str:
    """Render a full memory snapshot as plain text.

    Empty groups (no nodes matching the filter) are omitted.
    """
    target_groups = groups if groups is not None else list(store.groups)

    sections: list[str] = []
    total = 0
    for group in target_groups:
        block = export_group(
            store,
            group,
            statuses=statuses,
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

    header = f"# zhar memory — {total} nodes\n"
    return header + "\n" + "\n\n".join(sections)


# ── helpers ───────────────────────────────────────────────────────────────────

def _sort_nodes(nodes: list[Node]) -> list[Node]:
    """Sort by node_type then created_at for stable output."""
    return sorted(nodes, key=lambda n: (n.node_type, n.created_at))


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
