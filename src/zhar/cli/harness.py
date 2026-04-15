"""Repo-centric harness CLI commands for mirrored files and context export."""

from __future__ import annotations

from pathlib import Path

import click

from zhar.cli.common import open_store
from zhar.harness.getter import get_harness_entry, list_harness_entries, read_harness_file
from zhar.harness.installer import export_mem_context_file, install_context_file
from zhar.harness.paths import default_context_output_path
from zhar.utils.facts import load_effective_facts, project_facts_path


def _flattened_key_help() -> str:
    """Return dynamic help text listing flattened harness keys and summaries."""
    lines = ["Print a mirrored harness file by flattened key.", "", "Available keys:"]
    for entry in list_harness_entries():
        summary = entry.summary or entry.description or "No description."
        lines.append(f"  {entry.key}")
        lines.append(f"    {summary}")
    return "\n".join(lines)


@click.group(name="harness")
@click.pass_context
def harness_group(ctx: click.Context) -> None:
    """Work with repo-centric harness files and legacy memory-context export."""


@harness_group.command("get", help=_flattened_key_help())
@click.argument("key")
def harness_get(key: str) -> None:
    """Print the mirrored harness file addressed by flattened *key*."""
    try:
        content = read_harness_file(key)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(content, nl=False)


@harness_group.command("export-mem-context")
@click.option(
    "--out",
    default=None,
    type=click.Path(),
    metavar="FILE",
    help="Output path (default: .github/agents/zhar-context.agent.md).",
)
@click.pass_context
def export_mem_context(ctx: click.Context, out: str | None) -> None:
    """Write the generated legacy memory-context file from live memory and facts."""
    store, zhar_root = open_store(ctx.obj["root"])
    facts = load_effective_facts(project_facts_path(zhar_root))
    output = Path(out) if out else default_context_output_path()
    export_mem_context_file(store, facts, output)
    click.echo(f"Written: {output}  ({output.stat().st_size} bytes)")


@harness_group.command("install")
@click.argument("target", type=click.Choice(["context"]))
@click.option(
    "--out",
    default=None,
    type=click.Path(),
    metavar="FILE",
    help="Output path (default: .github/agents/zhar-context.agent.md).",
)
@click.pass_context
def harness_install(ctx: click.Context, target: str, out: str | None) -> None:
    """Install supported legacy harness outputs such as the memory-context file."""
    del target
    store, zhar_root = open_store(ctx.obj["root"])
    facts = load_effective_facts(project_facts_path(zhar_root))
    output = Path(out) if out else default_context_output_path()
    install_context_file(store, facts, output)
    click.echo(f"Written: {output}  ({output.stat().st_size} bytes)")


def register_harness_commands(cli_group: click.Group) -> None:
    """Register the harness command group on *cli_group*."""
    cli_group.add_command(harness_group)