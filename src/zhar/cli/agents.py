"""Agent-related CLI commands: install, uninstall, and get."""

from __future__ import annotations

from pathlib import Path

import click

from zhar.cli.common import open_store
from zhar.mem.query import Query
from zhar.stack.bucket import BucketManager
from zhar.stack.registry import StackRegistry
from zhar.stack.render import render_installed_item
from zhar.utils.facts import load_effective_facts, project_facts_path


@click.group(name="agent")
@click.pass_context
def agent_group(ctx: click.Context) -> None:
    """Manage agent, instruction, skill, and hook items."""


@agent_group.command("get")
@click.argument("name")
@click.option(
    "--cache-dir",
    default=None,
    type=click.Path(),
    metavar="DIR",
    help="Override the bucket cache directory (default: ~/.zhar/stack/).",
)
@click.pass_context
def agent_get(ctx: click.Context, name: str, cache_dir: str | None) -> None:
    """Render a named installed item from source with current workspace facts.

    This command is a read-only runtime render of an installed stack item.
    It shares the same template parser and chunk resolution as stack sync,
    while keeping ``%%ZHAR.RSKILL%%`` lazy so output matches live runtime
    behavior for ``agent get`` and ``stack fetch``.
    """
    _, zhar_root = open_store(ctx.obj["root"])

    reg = StackRegistry(zhar_root / "cfg" / "stack.json")

    bm_kwargs: dict = {}
    if cache_dir is not None:
        bm_kwargs["cache_dir"] = Path(cache_dir)
    bm = BucketManager(**bm_kwargs)

    # Build current-workspace facts + memory context
    facts = load_effective_facts(project_facts_path(zhar_root))
    store, _ = open_store(ctx.obj["root"])
    groups = {g: store.query(Query(groups=[g])) for g in store.groups}

    try:
        rendered = render_installed_item(
            reg,
            bm,
            name,
            facts=facts,
            groups=groups,
            expand_skills=False,
        )
    except (FileNotFoundError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(rendered.rendered, nl=False)


def register_agent_commands(cli_group: click.Group) -> None:
    """Register the agent command group on *cli_group*."""
    cli_group.add_command(agent_group)
