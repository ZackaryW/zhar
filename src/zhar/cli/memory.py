"""Core memory-management CLI commands for zhar."""
# %ZHAR:db71%

from __future__ import annotations

import os
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


def _resolve_note_body(content: str | None, from_env: str | None) -> str:
    """Resolve note body text from a literal argument, stdin, or environment variable."""
    if from_env is not None and content is not None:
        raise click.UsageError("Provide either CONTENT or --from-env, not both.")
    if from_env is not None:
        try:
            return os.environ[from_env]
        except KeyError as exc:
            raise click.UsageError(f"Environment variable {from_env!r} is not set.") from exc
    if content is None:
        raise click.UsageError("Missing CONTENT. Provide text, '-', or --from-env NAME.")
    return click.get_text_stream("stdin").read() if content == "-" else content


def _get_node_or_exit(ctx: click.Context, node_id: str):
    """Return an existing node for *node_id* or exit with a user-facing error."""
    store, _ = open_store(ctx.obj["root"])
    node = store.get(node_id)
    if node is None:
        click.echo(f"Error: node '{node_id}' not found.", err=True)
        sys.exit(1)
    return store, node


def _build_query(
    *,
    group: tuple[str, ...],
    node_type: tuple[str, ...],
    status: tuple[str, ...],
    tag: tuple[str, ...],
    text: str | None,
    limit: int | None,
) -> Query:
    """Build a Query from CLI selector options."""
    return Query(
        groups=list(group) or None,
        node_types=list(node_type) or None,
        statuses=list(status) or None,
        tags=list(tag) or None,
        summary_contains=text,
        limit=limit,
    )


def _ensure_prune_filters(query: Query) -> None:
    """Reject prune requests that do not provide any narrowing filter."""
    has_selector = any([
        query.groups,
        query.node_types,
        query.statuses,
        query.tags,
        query.summary_contains,
        query.limit is not None,
    ])
    if not has_selector:
        raise click.UsageError(
            "prune requires at least one filter such as --group, --type, --status, --tag, --q, or --limit."
        )


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
@click.option("--status", default=None, metavar="STATUS", help="Explicit initial status (default: node type default).")
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
    status: str | None,
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
        status=status or type_def.default_status,
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
@click.argument("content", required=False)
@click.option(
    "--from-env",
    default=None,
    metavar="NAME",
    help="Read the note body from environment variable NAME.",
)
@click.pass_context
def note_command(
    ctx: click.Context,
    node_id: str,
    content: str | None,
    from_env: str | None,
) -> None:
    """Attach or replace the markdown body of a memory-backed node."""
    try:
        body = _resolve_note_body(content, from_env)
    except click.UsageError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
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


@click.command(name="set-status")
@click.argument("node_id")
@click.argument("status")
@click.pass_context
def set_status_command(ctx: click.Context, node_id: str, status: str) -> None:
    """Update the status of an existing node."""
    store, node = _get_node_or_exit(ctx, node_id)
    try:
        updated = patch_node(node, status=status)
        store.save(updated)
    except ValueError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Updated {node_id}  status={status}")


@click.command(name="remove")
@click.argument("node_id")
@click.pass_context
def remove_command(ctx: click.Context, node_id: str) -> None:
    """Delete one node by ID."""
    store, _ = _get_node_or_exit(ctx, node_id)
    deleted = store.delete(node_id)
    if not deleted:
        click.echo(f"Error: node '{node_id}' not found.", err=True)
        sys.exit(1)
    click.echo(f"Removed {node_id}")


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


@click.command(name="prune")
@click.option("--group", "group", multiple=True, metavar="NAME", help="Filter by group (repeatable).")
@click.option("--type", "node_type", multiple=True, metavar="NAME", help="Filter by node type (repeatable).")
@click.option("--status", multiple=True, metavar="STATUS", help="Filter by status (repeatable).")
@click.option("--tag", "tag", multiple=True, metavar="TAG", help="Node must have all listed tags (repeatable).")
@click.option("--q", "text", default=None, metavar="TEXT", help="Fuzzy summary search.")
@click.option("--limit", default=None, type=int, metavar="N", help="Max results to remove.")
@click.option("--dry-run", is_flag=True, help="Report matching nodes without deleting them.")
@click.pass_context
def prune_command(
    ctx: click.Context,
    group: tuple[str, ...],
    node_type: tuple[str, ...],
    status: tuple[str, ...],
    tag: tuple[str, ...],
    text: str | None,
    limit: int | None,
    dry_run: bool,
) -> None:
    """Delete all nodes that match the provided filters."""
    store, _ = open_store(ctx.obj["root"])
    query = _build_query(
        group=group,
        node_type=node_type,
        status=status,
        tag=tag,
        text=text,
        limit=limit,
    )
    try:
        _ensure_prune_filters(query)
    except click.UsageError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    nodes = store.query(query)
    if dry_run:
        click.echo(f"[dry-run] Would remove {len(nodes)} node(s).")
        for node in nodes:
            click.echo(f"  {node.id}  {node.group}/{node.node_type}  {node.status}  {node.summary!r}")
        return

    removed = 0
    for node in nodes:
        if store.delete(node.id):
            removed += 1

    click.echo(f"Removed {removed} node(s).")


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
@click.option("--tag", "tag", multiple=True, metavar="TAG", help="Node must have all listed tags (repeatable).")
@click.option("--relation-depth", default=0, type=int, metavar="N", help="Expand adjacent architecture_context/component_rel nodes up to depth N.")
@click.option("--with-runtime-context/--no-runtime-context", default=False, help="Include runtime context gathered from group-defined tools.")
@click.option("--out", default=None, type=click.Path(), metavar="FILE", help="Write output to FILE instead of stdout.")
@click.pass_context
def export_command(
    ctx: click.Context,
    group: tuple[str, ...],
    status: tuple[str, ...],
    tag: tuple[str, ...],
    relation_depth: int,
    with_runtime_context: bool,
    out: str | None,
) -> None:
    """Print a memory snapshot for agent context injection."""
    store, zhar_root = open_store(ctx.obj["root"])
    text = export_text(
        store,
        groups=list(group) or None,
        statuses=list(status) or None,
        tags=list(tag) or None,
        relation_depth=relation_depth,
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
    cli_group.add_command(set_status_command)
    cli_group.add_command(remove_command)
    cli_group.add_command(show_command)
    cli_group.add_command(query_command)
    cli_group.add_command(prune_command)
    cli_group.add_command(status_command)
    cli_group.add_command(scan_command)
    cli_group.add_command(export_command)
    cli_group.add_command(gc_command)
    cli_group.add_command(verify_command)
    cli_group.add_command(migrate_group)