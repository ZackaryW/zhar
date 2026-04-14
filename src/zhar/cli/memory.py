"""Core memory-management CLI commands for zhar."""
# %ZHAR:db71%

from __future__ import annotations

import sys
from pathlib import Path

import click

from zhar.cli.common import format_node, open_store, parse_meta, parse_target_ids
from zhar.mem.export import export_text
from zhar.mem.gc import run_gc
from zhar.mem.group import validate_node_metadata
from zhar.mem.node import make_node, patch_node
from zhar.mem.query import Query
from zhar.mem.scan import scan_tree, sync_sources
from zhar.mem.verify import Severity, run_verify
from zhar.migration.zmem import migrate_zmem_json
from zhar.utils.fs import ensure_gitignore_entry


@click.command(name="init")
@click.pass_context
def init_command(ctx: click.Context) -> None:
    """Create .zhar/ structure and update .gitignore."""
    root_opt: str | None = ctx.obj["root"]
    zhar_root = Path(root_opt) if root_opt else Path.cwd() / ".zhar"
    (zhar_root / "mem").mkdir(parents=True, exist_ok=True)
    (zhar_root / "cfg").mkdir(parents=True, exist_ok=True)
    ensure_gitignore_entry(zhar_root.parent, ".zhar/**/__pycache__/")
    click.echo(f"Initialised zhar at {zhar_root}")


@click.command(name="add")
@click.argument("group")
@click.argument("node_type")
@click.argument("summary")
@click.option("--meta", "meta", multiple=True, metavar="KEY=VALUE", help="Metadata field (repeatable). e.g. --meta severity=high")
@click.option("--tag", "tag", multiple=True, metavar="NAME", help="Tag (repeatable). e.g. --tag auth --tag perf")
@click.option("--source", default=None, metavar="PATH", help="Source file reference.")
@click.option("--content", default=None, metavar="TEXT", help="Markdown body (memory-backed types only). Use '-' to read stdin.")
@click.pass_context
def add_command(
    ctx: click.Context,
    group: str,
    node_type: str,
    summary: str,
    meta: tuple[str, ...],
    tag: tuple[str, ...],
    source: str | None,
    content: str | None,
) -> None:
    """Add a new memory node."""
    try:
        metadata = parse_meta(meta)
    except click.UsageError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    body = click.get_text_stream("stdin").read() if content == "-" else content
    store, _ = open_store(ctx.obj["root"])

    if group not in store.groups:
        click.echo(f"Error: unknown group '{group}'. Known: {list(store.groups)}", err=True)
        sys.exit(1)

    try:
        type_def = store.groups[group].get_type(node_type)
    except KeyError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    errors = validate_node_metadata(type_def, metadata)
    if errors:
        for error in errors:
            click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    node = make_node(
        group=group,
        node_type=node_type,
        summary=summary,
        tags=list(tag),
        source=source,
        content=body,
        metadata=metadata,
        node_id=store.allocate_id(),
    )

    try:
        store.save(node)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Added {node.id}  [{group}/{node_type}]  {summary!r}")


@click.command(name="add-note")
@click.argument("target_id")
@click.argument("content")
@click.option("--target", "extra_targets", multiple=True, metavar="NODE_ID", help="Additional node to attach this note to (repeatable).")
@click.pass_context
def add_note_command(
    ctx: click.Context,
    target_id: str,
    content: str,
    extra_targets: tuple[str, ...],
) -> None:
    """Create a supplemental note attached to one or more existing nodes."""
    body = click.get_text_stream("stdin").read() if content == "-" else content
    store, _ = open_store(ctx.obj["root"])

    target_ids = [target_id, *extra_targets]
    unique_targets: list[str] = []
    for candidate in target_ids:
        if candidate not in unique_targets:
            unique_targets.append(candidate)

    for candidate in unique_targets:
        node = store.get(candidate)
        if node is None:
            click.echo(f"Error: node '{candidate}' not found.", err=True)
            sys.exit(1)
        if node.group == "notes":
            click.echo("Error: note nodes cannot target other note nodes.", err=True)
            sys.exit(1)

    note = make_node(
        group="notes",
        node_type="note",
        summary=(body.splitlines()[0].strip() if body.strip() else f"Attached note for {target_id}"),
        content=body,
        metadata={"agent": "copilot", "target_ids": ",".join(unique_targets)},
        node_id=store.allocate_id(),
    )

    try:
        store.save(note)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Added {note.id}  [notes/note]  targets={','.join(unique_targets)!r}")


@click.command(name="note")
@click.argument("node_id")
@click.argument("content")
@click.pass_context
def note_command(ctx: click.Context, node_id: str, content: str) -> None:
    """Attach or replace the markdown body of a memory-backed node."""
    body = click.get_text_stream("stdin").read() if content == "-" else content
    store, _ = open_store(ctx.obj["root"])
    node = store.get(node_id)
    if node is None:
        click.echo(f"Error: node '{node_id}' not found.", err=True)
        sys.exit(1)

    type_def = store.groups[node.group].get_type(node.node_type)
    if not type_def.memory_backed:
        click.echo(
            f"Error: node type '{node.node_type}' in group '{node.group}' is not "
            f"memory_backed — cannot attach content.",
            err=True,
        )
        sys.exit(1)

    store.save(patch_node(node, content=body))
    click.echo(f"Updated {node_id}  (content set, {len(body)} chars)")


@click.command(name="show")
@click.argument("node_id")
@click.pass_context
def show_command(ctx: click.Context, node_id: str) -> None:
    """Display all fields of a node."""
    store, _ = open_store(ctx.obj["root"])
    node = store.get(node_id)
    if node is None:
        click.echo(f"Error: node '{node_id}' not found.", err=True)
        sys.exit(1)
    click.echo(format_node(node))


@click.command(name="query")
@click.option("--group", "group", multiple=True, metavar="NAME", help="Filter by group (repeatable).")
@click.option("--type", "node_type", multiple=True, metavar="NAME", help="Filter by node type (repeatable).")
@click.option("--status", multiple=True, metavar="STATUS", help="Filter by status (repeatable).")
@click.option("--tag", "tag", multiple=True, metavar="TAG", help="Node must have all listed tags (repeatable).")
@click.option("--q", "text", default=None, metavar="TEXT", help="Fuzzy summary search.")
@click.option("--note-depth", default=0, type=int, metavar="N", help="Show attached notes under each matched node up to depth N (default: 0).")
@click.option("--limit", default=None, type=int, metavar="N", help="Max results.")
@click.pass_context
def query_command(
    ctx: click.Context,
    group: tuple[str, ...],
    node_type: tuple[str, ...],
    status: tuple[str, ...],
    tag: tuple[str, ...],
    text: str | None,
    note_depth: int,
    limit: int | None,
) -> None:
    """Search and filter memory nodes."""
    store, _ = open_store(ctx.obj["root"])
    selected_groups = list(group) or None
    selected_types = list(node_type) or None
    if selected_groups is None and selected_types is None:
        selected_groups = [name for name in store.groups if name != "notes"]

    nodes = store.query(
        Query(
            groups=selected_groups,
            node_types=selected_types,
            statuses=list(status) or None,
            tags=list(tag) or None,
            summary_contains=text,
            limit=limit,
        )
    )
    if not nodes:
        click.echo("No results.")
        return

    for node in nodes:
        meta_str = ""
        if node.metadata:
            meta_str = "  " + "  ".join(f"{key}={value}" for key, value in node.metadata.items())
        tag_str = f"  [{', '.join(node.tags)}]" if node.tags else ""
        click.echo(
            f"{node.id}  {node.group}/{node.node_type}  {node.status}  "
            f"{node.summary!r}{tag_str}{meta_str}"
        )
        if note_depth > 0 and node.group != "notes":
            for note in store.attached_notes(node.id):
                click.echo(f"  note {note.id}  {note.summary!r}")
                if note.content:
                    for line in note.content.splitlines():
                        click.echo(f"    {line}")


@click.command(name="status")
@click.pass_context
def status_command(ctx: click.Context) -> None:
    """Show per-group node counts."""
    store, _ = open_store(ctx.obj["root"])
    stats = store.stats()
    click.echo(f"Total nodes: {sum(value['total'] for value in stats.values())}\n")
    for group_name, data in stats.items():
        click.echo(f"  {group_name}  ({data['total']})")
        for type_name, count in data["by_type"].items():
            marker = " *" if count and store.groups[group_name].get_type(type_name).singleton else ""
            click.echo(f"    {type_name:<25} {count}{marker}")


@click.command(name="scan")
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--ext", multiple=True, metavar="EXT", help="File extension to scan (default: common source extensions). e.g. --ext .py --ext .ts")
@click.option("--dry-run", is_flag=True, help="Report hits without updating nodes.")
@click.pass_context
def scan_command(ctx: click.Context, path: str, ext: tuple[str, ...], dry_run: bool) -> None:
    """Scan source files for %ZHAR markers and sync node sources."""
    store, _ = open_store(ctx.obj["root"])
    hits = scan_tree(Path(path), extensions=set(ext) if ext else None)
    if not hits:
        click.echo("No markers found.")
        return

    click.echo(f"Found {len(hits)} marker(s).")
    for hit in hits:
        click.echo(f"  {hit.path}:{hit.line}  {hit.node_id}")

    if dry_run:
        return

    report = sync_sources(store, hits)
    click.echo(f"\nSynced: {report['updated']} updated, {report['skipped']} skipped (unknown IDs).")


@click.command(name="export")
@click.option("--group", "group", multiple=True, metavar="NAME", help="Limit to specific groups (repeatable).")
@click.option("--status", multiple=True, metavar="STATUS", help="Limit to specific statuses (default: all).")
@click.option("--with-runtime-context/--no-runtime-context", default=False, help="Include runtime context gathered from group-defined tools.")
@click.option("--out", default=None, type=click.Path(), metavar="FILE", help="Write output to FILE instead of stdout.")
@click.pass_context
def export_command(
    ctx: click.Context,
    group: tuple[str, ...],
    status: tuple[str, ...],
    with_runtime_context: bool,
    out: str | None,
) -> None:
    """Print a memory snapshot for agent context injection."""
    store, zhar_root = open_store(ctx.obj["root"])
    text = export_text(
        store,
        groups=list(group) or None,
        statuses=list(status) or None,
        include_runtime_context=with_runtime_context,
        project_root=zhar_root.parent,
    )
    if out:
        Path(out).write_text(text, encoding="utf-8")
        click.echo(f"Written to {out}")
        return
    click.echo(text)


@click.command(name="gc")
@click.option("--dry-run", is_flag=True, help="Report what would be removed without doing it.")
@click.pass_context
def gc_command(ctx: click.Context, dry_run: bool) -> None:
    """Expire and archive stale nodes."""
    store, _ = open_store(ctx.obj["root"])
    report = run_gc(store, dry_run=dry_run)
    prefix = "[dry-run] " if dry_run else ""
    click.echo(f"{prefix}Expired: {report.expired}  Archived: {report.archived}  Total: {report.total}")


@click.command(name="verify")
@click.option("--project-root", default=".", type=click.Path(exists=True, file_okay=False), metavar="PATH", help="Project root for source file checks (default: cwd).")
@click.pass_context
def verify_command(ctx: click.Context, project_root: str) -> None:
    """Run completeness and consistency checks."""
    store, _ = open_store(ctx.obj["root"])
    issues = run_verify(store, project_root=Path(project_root))
    if not issues:
        click.echo("✓ No issues found.")
        return

    errors = [issue for issue in issues if issue.severity == Severity.ERROR]
    warns = [issue for issue in issues if issue.severity == Severity.WARN]
    infos = [issue for issue in issues if issue.severity == Severity.INFO]
    for issue in errors + warns + infos:
        prefix = {"error": "✗", "warn": "⚠", "info": "·"}[issue.severity.value]
        click.echo(f"{prefix} [{issue.code}] {issue.message}")
    if errors:
        sys.exit(1)


@click.group(name="migrate")
def migrate_group() -> None:
    """Import external memory formats into the current zhar store."""


@migrate_group.command(name="zmem")
@click.argument("source_path", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def migrate_zmem_command(ctx: click.Context, source_path: Path) -> None:
    """Migrate a zmem graph.json surface into the current zhar store."""
    store, _ = open_store(ctx.obj["root"])
    report = migrate_zmem_json(store, source_path)
    click.echo(
        f"Migrated {report.migrated_nodes} node(s), created {report.created_notes} note(s), "
        f"reused {report.preserved_ids} legacy id(s)."
    )


def register_memory_commands(cli_group: click.Group) -> None:
    """Register the core memory CLI commands on *cli_group*."""
    cli_group.add_command(init_command)
    cli_group.add_command(add_command)
    cli_group.add_command(add_note_command)
    cli_group.add_command(note_command)
    cli_group.add_command(show_command)
    cli_group.add_command(query_command)
    cli_group.add_command(status_command)
    cli_group.add_command(scan_command)
    cli_group.add_command(export_command)
    cli_group.add_command(gc_command)
    cli_group.add_command(verify_command)
    cli_group.add_command(migrate_group)