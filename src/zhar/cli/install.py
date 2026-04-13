"""Installer-related CLI commands for zhar."""

from __future__ import annotations

from pathlib import Path

import click

from zhar.cli.common import open_store
from zhar.agents.installer import install_agent_file, uninstall_agent_file
from zhar.utils.facts import Facts


@click.command(name="install")
@click.option("--out", default=None, type=click.Path(), metavar="FILE", help="Output path (default: .github/agents/zhar.agent.md).")
@click.pass_context
def install_command(ctx: click.Context, out: str | None) -> None:
    """Write the agent instruction file from memory and facts."""
    store, zhar_root = open_store(ctx.obj["root"])
    facts_path = zhar_root / "facts.json"
    facts = Facts(facts_path) if facts_path.exists() else None
    output = Path(out) if out else Path(".github") / "agents" / "zhar.agent.md"
    install_agent_file(store, facts, output)
    click.echo(f"Written: {output}  ({output.stat().st_size} bytes)")


@click.command(name="uninstall")
@click.option("--out", default=None, type=click.Path(), metavar="FILE", help="Path to remove (default: .github/agents/zhar.agent.md).")
@click.pass_context
def uninstall_command(ctx: click.Context, out: str | None) -> None:
    """Remove the generated agent instruction file."""
    output = Path(out) if out else Path(".github") / "agents" / "zhar.agent.md"
    if uninstall_agent_file(output):
        click.echo(f"Removed: {output}")
        return
    click.echo(f"Not found: {output}")


def register_install_commands(cli_group: click.Group) -> None:
    """Register install-related commands on *cli_group*."""
    cli_group.add_command(install_command)
    cli_group.add_command(uninstall_command)