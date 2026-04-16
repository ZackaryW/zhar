"""Repo-centric harness CLI commands for mirrored files and context export."""

from __future__ import annotations

from pathlib import Path

import click

from zhar.cli.common import open_store
from zhar.harness.getter import get_harness_entry, list_harness_entries, read_harness_file
from zhar.harness.installer import export_mem_context_file, install_harness_entry
from zhar.harness.paths import default_context_output_path
from zhar.utils.facts import load_effective_facts, project_facts_path


def _flattened_key_rows() -> list[tuple[str, str]]:
    """Return flattened harness keys and summaries for CLI help rendering."""
    rows: list[tuple[str, str]] = []
    for entry in list_harness_entries():
        summary = entry.summary or entry.description or "No description."
        rows.append((entry.key, summary))
    return rows


class HarnessKeyCommand(click.Command):
    """Render dynamic help with a readable available-keys section."""

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Write command help plus a definition list of available flattened keys."""
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_options(ctx, formatter)
        rows = _flattened_key_rows()
        if rows:
            with formatter.section("Available keys"):
                formatter.write_dl(rows)
        self.format_epilog(ctx, formatter)


@click.group(name="harness")
@click.pass_context
def harness_group(ctx: click.Context) -> None:
    """Work with repo-centric harness files and legacy memory-context export."""


@harness_group.command(
    "get",
    cls=HarnessKeyCommand,
    help="Print a mirrored harness file by flattened key.",
)
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


@harness_group.command(
    "install",
    cls=HarnessKeyCommand,
    help="Install a mirrored harness file by flattened key into the workspace.",
)
@click.argument("key")
@click.option(
    "--out",
    default=None,
    type=click.Path(),
    metavar="FILE",
    help="Output path (default: matching .github destination for the flattened key).",
)
def harness_install(key: str, out: str | None) -> None:
    """Install a mirrored harness file by flattened key into the workspace."""
    if key == "context":
        raise click.ClickException(
            "Legacy 'harness install context' moved to 'zhar harness export-mem-context'."
        )

    try:
        entry = get_harness_entry(key)
    except KeyError as exc:
        raise click.ClickException(str(exc)) from exc

    output = Path(out) if out else None
    written = install_harness_entry(entry, output)
    click.echo(f"Written: {written}  ({written.stat().st_size} bytes)")


def register_harness_commands(cli_group: click.Group) -> None:
    """Register the harness command group on *cli_group*."""
    cli_group.add_command(harness_group)