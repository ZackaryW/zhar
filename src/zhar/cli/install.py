"""Legacy installer-related CLI commands for generated memory-context files."""

from __future__ import annotations

from pathlib import Path

import click

from zhar.cli.common import open_store
from zhar.harness.installer import install_agent_file, uninstall_agent_file
from zhar.harness.paths import default_context_output_path
from zhar.utils.facts import load_effective_facts, project_facts_path


@click.command(name="install")
@click.option("--out", default=None, type=click.Path(), metavar="FILE", help="Output path (default: .github/agents/zhar-context.agent.md).")
@click.pass_context
def install_command(ctx: click.Context, out: str | None) -> None:
    """Write the generated legacy memory-context file from memory and facts."""
    store, zhar_root = open_store(ctx.obj["root"])
    facts = load_effective_facts(project_facts_path(zhar_root))
    output = Path(out) if out else default_context_output_path()
    install_agent_file(store, facts, output)
    click.echo(f"Written: {output}  ({output.stat().st_size} bytes)")


@click.command(name="uninstall")
@click.option("--out", default=None, type=click.Path(), metavar="FILE", help="Path to remove (default: .github/agents/zhar-context.agent.md).")
@click.pass_context
def uninstall_command(ctx: click.Context, out: str | None) -> None:
    """Remove the generated legacy memory-context file."""
    output = Path(out) if out else default_context_output_path()
    if uninstall_agent_file(output):
        click.echo(f"Removed: {output}")
        return
    click.echo(f"Not found: {output}")


def register_install_commands(cli_group: click.Group) -> None:
    """Register install-related commands on *cli_group*."""
    cli_group.add_command(install_command)
    cli_group.add_command(uninstall_command)