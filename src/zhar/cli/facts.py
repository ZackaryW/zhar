"""Facts CLI commands for zhar."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from zhar.utils.config import find_zhar_root
from zhar.utils.facts import Facts, global_facts_path, load_effective_facts, project_facts_path

_READ_SCOPES = click.Choice(["effective", "project", "global"], case_sensitive=False)
_WRITE_SCOPES = click.Choice(["project", "global"], case_sensitive=False)


def _resolve_project_facts_path(root: str | None) -> Path:
    """Return the project facts path for the current CLI context."""
    if root:
        return project_facts_path(Path(root))
    found = find_zhar_root(Path.cwd())
    zhar_root = found if found else Path.cwd() / ".zhar"
    return project_facts_path(zhar_root)


def _read_scope_data(ctx: click.Context, scope: str) -> dict[str, str]:
    """Return facts visible for *scope* in the current CLI context."""
    project_path = _resolve_project_facts_path(ctx.obj["root"])
    if scope == "global":
        return Facts(global_facts_path()).all() if global_facts_path().exists() else {}
    if scope == "project":
        return Facts(project_path).all() if project_path.exists() else {}
    return load_effective_facts(project_path)


def _write_scope_store(ctx: click.Context, scope: str) -> Facts:
    """Return the writable facts store for *scope* in the current CLI context."""
    if scope == "global":
        return Facts(global_facts_path())
    return Facts(_resolve_project_facts_path(ctx.obj["root"]))


@click.group(name="facts")
@click.pass_context
def facts_group(ctx: click.Context) -> None:
    """Manage project and global facts."""


@facts_group.command("set")
@click.option(
    "--scope",
    type=_WRITE_SCOPES,
    default="project",
    show_default=True,
    help="Write to the selected facts scope.",
)
@click.argument("key")
@click.argument("value")
@click.pass_context
def facts_set(ctx: click.Context, scope: str, key: str, value: str) -> None:
    """Set a fact value."""
    facts = _write_scope_store(ctx, scope)
    facts.set(key, value)
    click.echo(f"Set {scope} fact {key!r} = {value!r}")


@facts_group.command("get")
@click.option(
    "--scope",
    type=_READ_SCOPES,
    default="effective",
    show_default=True,
    help="Read from the selected facts scope.",
)
@click.argument("key")
@click.pass_context
def facts_get(ctx: click.Context, scope: str, key: str) -> None:
    """Get a fact value by key."""
    value = _read_scope_data(ctx, scope).get(key)
    if value is None:
        click.echo("(not set)", err=True)
        sys.exit(1)
    click.echo(value)


@facts_group.command("unset")
@click.option(
    "--scope",
    type=_WRITE_SCOPES,
    default="project",
    show_default=True,
    help="Remove from the selected facts scope.",
)
@click.argument("key")
@click.pass_context
def facts_unset(ctx: click.Context, scope: str, key: str) -> None:
    """Remove a fact by key."""
    facts = _write_scope_store(ctx, scope)
    facts.unset(key)
    click.echo(f"Unset {scope} fact {key!r}")


@facts_group.command("list")
@click.option(
    "--scope",
    type=_READ_SCOPES,
    default="effective",
    show_default=True,
    help="List facts from the selected scope.",
)
@click.pass_context
def facts_list(ctx: click.Context, scope: str) -> None:
    """List all facts."""
    data = _read_scope_data(ctx, scope)
    if not data:
        click.echo("(no facts set)")
        return
    for key, value in sorted(data.items()):
        click.echo(f"{key} = {value}")


def register_facts_commands(cli_group: click.Group) -> None:
    """Register the facts command group on *cli_group*."""
    cli_group.add_command(facts_group)