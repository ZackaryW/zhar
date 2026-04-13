"""Facts CLI commands for zhar."""

from __future__ import annotations

import sys

import click

from zhar.cli.common import open_store
from zhar.utils.facts import Facts


@click.group(name="facts")
@click.pass_context
def facts_group(ctx: click.Context) -> None:
    """Manage project facts (independent key-value store)."""


@facts_group.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def facts_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a fact value."""
    _, zhar_root = open_store(ctx.obj["root"])
    facts = Facts(zhar_root / "facts.json")
    facts.set(key, value)
    click.echo(f"Set {key!r} = {value!r}")


@facts_group.command("get")
@click.argument("key")
@click.pass_context
def facts_get(ctx: click.Context, key: str) -> None:
    """Get a fact value by key."""
    _, zhar_root = open_store(ctx.obj["root"])
    facts = Facts(zhar_root / "facts.json")
    value = facts.get(key)
    if value is None:
        click.echo("(not set)", err=True)
        sys.exit(1)
    click.echo(value)


@facts_group.command("unset")
@click.argument("key")
@click.pass_context
def facts_unset(ctx: click.Context, key: str) -> None:
    """Remove a fact by key."""
    _, zhar_root = open_store(ctx.obj["root"])
    facts = Facts(zhar_root / "facts.json")
    facts.unset(key)
    click.echo(f"Unset {key!r}")


@facts_group.command("list")
@click.pass_context
def facts_list(ctx: click.Context) -> None:
    """List all facts."""
    _, zhar_root = open_store(ctx.obj["root"])
    facts = Facts(zhar_root / "facts.json")
    data = facts.all()
    if not data:
        click.echo("(no facts set)")
        return
    for key, value in sorted(data.items()):
        click.echo(f"{key} = {value}")


def register_facts_commands(cli_group: click.Group) -> None:
    """Register the facts command group on *cli_group*."""
    cli_group.add_command(facts_group)