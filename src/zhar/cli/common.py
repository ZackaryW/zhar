"""Shared helpers for the zhar CLI package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from zhar.mem.store import MemStore
from zhar.utils.config import find_zhar_root


def parse_meta(meta_pairs: tuple[str, ...]) -> dict[str, Any]:
    """Parse ``('k=v', ...)`` into a metadata dictionary."""
    result: dict[str, Any] = {}
    for pair in meta_pairs:
        if "=" not in pair:
            raise click.UsageError(
                f"--meta value {pair!r} must be in 'key=value' format."
            )
        key, _, value = pair.partition("=")
        result[key.strip()] = value.strip()
    return result


def open_store(root: str | None) -> tuple[MemStore, Path]:
    """Resolve the .zhar root and return ``(MemStore, root_path)``."""
    if root:
        zhar_root = Path(root)
    else:
        found = find_zhar_root(Path.cwd())
        zhar_root = found if found else Path.cwd() / ".zhar"
    return MemStore(zhar_root), zhar_root


def format_node(node) -> str:
    """Return a human-readable multi-line string for a node."""
    lines = [
        f"id:         {node.id}",
        f"group:      {node.group}",
        f"type:       {node.node_type}",
        f"status:     {node.status}",
        f"summary:    {node.summary}",
    ]
    if node.tags:
        lines.append(f"tags:       {', '.join(node.tags)}")
    if node.source:
        lines.append(f"source:     {node.source}")
    if node.metadata:
        for key, value in visible_metadata(node):
            lines.append(f"meta.{key:<8}{value}")
    if node.custom:
        for key, value in node.custom.items():
            lines.append(f"custom.{key:<7}{value}")
    lines.append(f"created:    {node.created_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"updated:    {node.updated_at.strftime('%Y-%m-%d %H:%M')}")
    if node.content is not None:
        lines.append("")
        lines.append("── content ──────────────────────────")
        lines.append(node.content)
    return "\n".join(lines)


def format_related_nodes(nodes) -> str:
    """Return a compact related-nodes section for show-style CLI output."""
    if not nodes:
        return ""

    lines = ["", "── related nodes ───────────────────"]
    for node in nodes:
        tag_str = f" [{', '.join(node.tags)}]" if node.tags else ""
        lines.append(f"[{node.id}] {node.group}/{node.node_type} {node.status} {node.summary!r}{tag_str}")
    return "\n".join(lines)


def visible_metadata(node) -> list[tuple[str, Any]]:
    """Return metadata items that should be shown in CLI output."""
    items = list(node.metadata.items())
    if node.group == "code_history" and node.node_type == "file_change" and node.source:
        return [(key, value) for key, value in items if key != "path"]
    return items


def parse_target_ids(value: str) -> list[str]:
    """Parse a comma-separated note target string into IDs."""
    return [part.strip() for part in value.split(",") if part.strip()]