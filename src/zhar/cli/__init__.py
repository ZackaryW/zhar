"""zhar CLI — manage project memory via the command line."""

from __future__ import annotations

import click

from zhar.cli.facts import register_facts_commands
from zhar.cli.install import register_install_commands
from zhar.cli.memory import register_memory_commands
from zhar.cli.stack import register_stack_commands


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


register_memory_commands(cli)
register_facts_commands(cli)
register_install_commands(cli)
register_stack_commands(cli)