"""zhar CLI — manage project memory via the command line.

Commands
--------
  init      Create .zhar/ structure and update .gitignore
  add       Save a new node
  note      Attach / replace markdown body on a memory-backed node
  show      Pretty-print a node by ID
  query     Filter and search nodes
  status    Show per-group node counts
  facts     Get / set / unset / list project facts
  scan      Scan source files for %ZHAR:<id>% markers and sync sources
  export    Print a memory snapshot suitable for agent context
  gc        Expire and archive stale nodes
  verify    Run completeness checks
  install   Write .github/agents/zhar.agent.md
  uninstall Remove .github/agents/zhar.agent.md

Global options
--------------
  --root PATH   Path to the .zhar/ root directory (default: auto-detect via
                find_zhar_root, falling back to ./.zhar/)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click

from zhar.harness.installer import install_agent_file, uninstall_agent_file
from zhar.mem.export import export_text
from zhar.mem.gc import run_gc
from zhar.mem.group import validate_node_metadata
from zhar.mem.node import make_node, patch_node
from zhar.mem.query import Query
from zhar.mem.scan import scan_tree, sync_sources
from zhar.mem.store import MemStore
from zhar.mem.verify import run_verify, Severity
from zhar.utils.config import find_zhar_root
from zhar.utils.facts import Facts
from zhar.utils.fs import ensure_gitignore_entry


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_meta(meta_pairs: tuple[str, ...]) -> dict[str, Any]:
    """Parse ``('k=v', ...)`` into a dict.  Raises UsageError on bad syntax."""
    result: dict[str, Any] = {}
    for pair in meta_pairs:
        if "=" not in pair:
            raise click.UsageError(
                f"--meta value {pair!r} must be in 'key=value' format."
            )
        k, _, v = pair.partition("=")
        result[k.strip()] = v.strip()
    return result


def _open_store(root: str | None) -> tuple[MemStore, Path]:
    """Resolve the .zhar root and return (MemStore, root_path)."""
    if root:
        zhar_root = Path(root)
    else:
        found = find_zhar_root(Path.cwd())
        zhar_root = found if found else Path.cwd() / ".zhar"
    return MemStore(zhar_root), zhar_root


def _format_node(node) -> str:
    """Return a human-readable multi-line string for a Node."""
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
        for k, v in node.metadata.items():
            lines.append(f"meta.{k:<8}{v}")
    if node.custom:
        for k, v in node.custom.items():
            lines.append(f"custom.{k:<7}{v}")
    lines.append(f"created:    {node.created_at.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"updated:    {node.updated_at.strftime('%Y-%m-%d %H:%M')}")
    if node.content is not None:
        lines.append("")
        lines.append("── content ──────────────────────────")
        lines.append(node.content)
    return "\n".join(lines)


# ── CLI root group ────────────────────────────────────────────────────────────

@click.group()
@click.option(
    "--root",
    default=None,
    metavar="PATH",
    help="Path to the .zhar/ directory (default: auto-detect).",
)
@click.pass_context
def cli(ctx: click.Context, root: str | None) -> None:
    """zhar — project memory tool."""
    ctx.ensure_object(dict)
    ctx.obj["root"] = root


# ── init ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Create .zhar/ structure and update .gitignore."""
    root_opt: str | None = ctx.obj["root"]
    zhar_root = Path(root_opt) if root_opt else Path.cwd() / ".zhar"

    # Create mem/ and cfg/ directories
    (zhar_root / "mem").mkdir(parents=True, exist_ok=True)
    (zhar_root / "cfg").mkdir(parents=True, exist_ok=True)

    # The .zhar/ directory itself is committed (it IS the project memory).
    # Only ignore Python bytecode that may be generated from user group files.
    project_root = zhar_root.parent
    ensure_gitignore_entry(project_root, ".zhar/**/__pycache__/")

    click.echo(f"Initialised zhar at {zhar_root}")


# ── add ───────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("group")
@click.argument("node_type")
@click.argument("summary")
@click.option("--meta", "-m", multiple=True, metavar="KEY=VALUE",
              help="Metadata field (repeatable). e.g. --meta severity=high")
@click.option("--tag", "-t", multiple=True, metavar="NAME",
              help="Tag (repeatable). e.g. --tag auth --tag perf")
@click.option("--source", "-s", default=None, metavar="PATH",
              help="Source file reference.")
@click.option("--content", "-c", default=None, metavar="TEXT",
              help="Markdown body (memory-backed types only). Use '-' to read stdin.")
@click.pass_context
def add(
    ctx: click.Context,
    group: str,
    node_type: str,
    summary: str,
    meta: tuple[str, ...],
    tag: tuple[str, ...],
    source: str | None,
    content: str | None,
) -> None:
    """Add a new memory node.

    \b
    Examples:
      zhar add project_dna core_requirement "Support TDD" --meta priority=high
      zhar add problem_tracking known_issue "OOM on scan" --meta severity=critical --tag ops
      zhar add decision_trail adr "Use orjson" --content "## Why\\n\\norjson is 3x faster."
    """
    # Parse --meta
    try:
        metadata = _parse_meta(meta)
    except click.UsageError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Read content from stdin if requested
    body: str | None = content
    if content == "-":
        body = click.get_text_stream("stdin").read()

    store, _ = _open_store(ctx.obj["root"])

    # Validate group + type exist
    if group not in store.groups:
        click.echo(f"Error: unknown group '{group}'. Known: {list(store.groups)}", err=True)
        sys.exit(1)

    group_def = store.groups[group]
    try:
        type_def = group_def.get_type(node_type)
    except KeyError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    # Validate metadata semantics
    errors = validate_node_metadata(type_def, metadata)
    if errors:
        for e in errors:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Build and save
    node = make_node(
        group=group,
        node_type=node_type,
        summary=summary,
        tags=list(tag),
        source=source,
        content=body,
        metadata=metadata,
    )

    try:
        store.save(node)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Added {node.id}  [{group}/{node_type}]  {summary!r}")


# ── note ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("node_id")
@click.argument("content")
@click.pass_context
def note(ctx: click.Context, node_id: str, content: str) -> None:
    """Attach or replace the markdown body of a memory-backed node.

    Use '-' as CONTENT to read from stdin.
    """
    body = click.get_text_stream("stdin").read() if content == "-" else content

    store, _ = _open_store(ctx.obj["root"])
    node = store.get(node_id)
    if node is None:
        click.echo(f"Error: node '{node_id}' not found.", err=True)
        sys.exit(1)

    # Check memory_backed
    type_def = store.groups[node.group].get_type(node.node_type)
    if not type_def.memory_backed:
        click.echo(
            f"Error: node type '{node.node_type}' in group '{node.group}' is not "
            f"memory_backed — cannot attach content.",
            err=True,
        )
        sys.exit(1)

    updated = patch_node(node, content=body)
    store.save(updated)
    click.echo(f"Updated {node_id}  (content set, {len(body)} chars)")


# ── show ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("node_id")
@click.pass_context
def show(ctx: click.Context, node_id: str) -> None:
    """Display all fields of a node."""
    store, _ = _open_store(ctx.obj["root"])
    node = store.get(node_id)
    if node is None:
        click.echo(f"Error: node '{node_id}' not found.", err=True)
        sys.exit(1)
    click.echo(_format_node(node))


# ── query ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--group", "-g", multiple=True, metavar="NAME",
              help="Filter by group (repeatable).")
@click.option("--type", "node_type", multiple=True, metavar="NAME",
              help="Filter by node type (repeatable).")
@click.option("--status", multiple=True, metavar="STATUS",
              help="Filter by status (repeatable).")
@click.option("--tag", "-t", multiple=True, metavar="TAG",
              help="Node must have all listed tags (repeatable).")
@click.option("--q", "text", default=None, metavar="TEXT",
              help="Fuzzy summary search.")
@click.option("--limit", default=None, type=int, metavar="N",
              help="Max results.")
@click.pass_context
def query(
    ctx: click.Context,
    group: tuple[str, ...],
    node_type: tuple[str, ...],
    status: tuple[str, ...],
    tag: tuple[str, ...],
    text: str | None,
    limit: int | None,
) -> None:
    """Search and filter memory nodes."""
    store, _ = _open_store(ctx.obj["root"])

    q = Query(
        groups=list(group) or None,
        node_types=list(node_type) or None,
        statuses=list(status) or None,
        tags=list(tag) or None,
        summary_contains=text,
        limit=limit,
    )
    nodes = store.query(q)
    if not nodes:
        click.echo("No results.")
        return

    for n in nodes:
        meta_str = ""
        if n.metadata:
            meta_str = "  " + "  ".join(f"{k}={v}" for k, v in n.metadata.items())
        tag_str = f"  [{', '.join(n.tags)}]" if n.tags else ""
        click.echo(f"{n.id}  {n.group}/{n.node_type}  {n.status}  {n.summary!r}{tag_str}{meta_str}")


# ── status ────────────────────────────────────────────────────────────────────

@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show per-group node counts."""
    store, _ = _open_store(ctx.obj["root"])
    stats = store.stats()

    total_all = sum(v["total"] for v in stats.values())
    click.echo(f"Total nodes: {total_all}\n")
    for group_name, data in stats.items():
        click.echo(f"  {group_name}  ({data['total']})")
        for type_name, count in data["by_type"].items():
            marker = " *" if count and store.groups[group_name].get_type(type_name).singleton else ""
            click.echo(f"    {type_name:<25} {count}{marker}")


# ── facts ─────────────────────────────────────────────────────────────────────

@cli.group()
@click.pass_context
def facts(ctx: click.Context) -> None:
    """Manage project facts (independent key-value store)."""


@facts.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def facts_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a fact: zhar facts set KEY VALUE"""
    _, zhar_root = _open_store(ctx.obj["root"])
    f = Facts(zhar_root / "facts.json")
    f.set(key, value)
    click.echo(f"Set {key!r} = {value!r}")


@facts.command("get")
@click.argument("key")
@click.pass_context
def facts_get(ctx: click.Context, key: str) -> None:
    """Get a fact value by key."""
    _, zhar_root = _open_store(ctx.obj["root"])
    f = Facts(zhar_root / "facts.json")
    val = f.get(key)
    if val is None:
        click.echo(f"(not set)", err=True)
        sys.exit(1)
    click.echo(val)


@facts.command("unset")
@click.argument("key")
@click.pass_context
def facts_unset(ctx: click.Context, key: str) -> None:
    """Remove a fact by key."""
    _, zhar_root = _open_store(ctx.obj["root"])
    f = Facts(zhar_root / "facts.json")
    f.unset(key)
    click.echo(f"Unset {key!r}")


@facts.command("list")
@click.pass_context
def facts_list(ctx: click.Context) -> None:
    """List all facts."""
    _, zhar_root = _open_store(ctx.obj["root"])
    f = Facts(zhar_root / "facts.json")
    data = f.all()
    if not data:
        click.echo("(no facts set)")
        return
    for k, v in sorted(data.items()):
        click.echo(f"{k} = {v}")


# ── scan ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--ext", multiple=True, metavar="EXT",
              help="File extension to scan (default: common source extensions). "
                   "e.g. --ext .py --ext .ts")
@click.option("--dry-run", is_flag=True, help="Report hits without updating nodes.")
@click.pass_context
def scan(ctx: click.Context, path: str, ext: tuple[str, ...], dry_run: bool) -> None:
    """Scan source files for %ZHAR:<id>% markers and sync node sources."""
    store, _ = _open_store(ctx.obj["root"])
    extensions = set(ext) if ext else None
    hits = scan_tree(Path(path), extensions=extensions)

    if not hits:
        click.echo("No markers found.")
        return

    click.echo(f"Found {len(hits)} marker(s).")
    for h in hits:
        click.echo(f"  {h.path}:{h.line}  {h.node_id}")

    if dry_run:
        return

    report = sync_sources(store, hits)
    click.echo(f"\nSynced: {report['updated']} updated, {report['skipped']} skipped (unknown IDs).")


# ── export ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--group", "-g", multiple=True, metavar="NAME",
              help="Limit to specific groups (repeatable).")
@click.option("--status", multiple=True, metavar="STATUS",
              help="Limit to specific statuses (default: all).")
@click.option("--out", default=None, type=click.Path(), metavar="FILE",
              help="Write output to FILE instead of stdout.")
@click.pass_context
def export(ctx: click.Context, group: tuple[str, ...], status: tuple[str, ...],
           out: str | None) -> None:
    """Print a memory snapshot for agent context injection."""
    store, _ = _open_store(ctx.obj["root"])
    text = export_text(
        store,
        groups=list(group) or None,
        statuses=list(status) or None,
    )
    if out:
        Path(out).write_text(text, encoding="utf-8")
        click.echo(f"Written to {out}")
    else:
        click.echo(text)


# ── gc ────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--dry-run", is_flag=True, help="Report what would be removed without doing it.")
@click.pass_context
def gc(ctx: click.Context, dry_run: bool) -> None:
    """Expire and archive stale nodes."""
    store, _ = _open_store(ctx.obj["root"])
    report = run_gc(store, dry_run=dry_run)
    prefix = "[dry-run] " if dry_run else ""
    click.echo(f"{prefix}Expired: {report.expired}  Archived: {report.archived}  Total: {report.total}")


# ── verify ────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--project-root", default=".", type=click.Path(exists=True, file_okay=False),
              metavar="PATH", help="Project root for source file checks (default: cwd).")
@click.pass_context
def verify(ctx: click.Context, project_root: str) -> None:
    """Run completeness and consistency checks."""
    store, _ = _open_store(ctx.obj["root"])
    issues = run_verify(store, project_root=Path(project_root))

    if not issues:
        click.echo("✓ No issues found.")
        return

    errors = [i for i in issues if i.severity == Severity.ERROR]
    warns  = [i for i in issues if i.severity == Severity.WARN]
    infos  = [i for i in issues if i.severity == Severity.INFO]

    for issue in errors + warns + infos:
        prefix = {"error": "✗", "warn": "⚠", "info": "·"}[issue.severity.value]
        click.echo(f"{prefix} [{issue.code}] {issue.message}")

    if errors:
        sys.exit(1)


# ── install / uninstall ───────────────────────────────────────────────────────

@cli.command()
@click.option("--out", default=None, type=click.Path(), metavar="FILE",
              help="Output path (default: .github/agents/zhar.agent.md).")
@click.pass_context
def install(ctx: click.Context, out: str | None) -> None:
    """Write the agent instruction file from memory + facts."""
    store, zhar_root = _open_store(ctx.obj["root"])
    facts_path = zhar_root / "facts.json"
    f = Facts(facts_path) if facts_path.exists() else None

    output = Path(out) if out else Path(".github") / "agents" / "zhar.agent.md"
    install_agent_file(store, f, output)
    click.echo(f"Written: {output}  ({output.stat().st_size} bytes)")


@cli.command()
@click.option("--out", default=None, type=click.Path(), metavar="FILE",
              help="Path to remove (default: .github/agents/zhar.agent.md).")
@click.pass_context
def uninstall(ctx: click.Context, out: str | None) -> None:
    """Remove the agent instruction file."""
    output = Path(out) if out else Path(".github") / "agents" / "zhar.agent.md"
    removed = uninstall_agent_file(output)
    if removed:
        click.echo(f"Removed: {output}")
    else:
        click.echo(f"Not found: {output}")
