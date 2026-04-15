"""zhar CLI — manage project memory via the command line."""

from __future__ import annotations

import click

from zhar.cli.agents import register_agent_commands
from zhar.cli.facts import register_facts_commands
from zhar.cli.harness import register_harness_commands
from zhar.cli.install import register_install_commands
from zhar.cli.memory import register_memory_commands
from zhar.cli.stack import register_stack_commands
from zhar.mem_session.cli import register_session_commands


class CategorizedGroup(click.Group):
    """Top-level Click group that renders commands grouped by category."""

    command_categories: dict[str, tuple[str, ...]] = {
        "Memory Commands": (
            "init",
            "add",
            "add-note",
            "note",
            "set-status",
            "remove",
            "show",
            "query",
            "prune",
            "status",
            "scan",
            "export",
            "gc",
            "verify",
            "migrate",
        ),
        "Facts Commands": (
            "facts",
        ),
        "Session Commands": (
            "session",
        ),
        "Agent Commands": (
            "agent",
            "install",
            "uninstall",
        ),
        "Harness Commands": (
            "harness",
        ),
        "Stack Commands": (
            "stack",
        ),
    }

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Render commands grouped by the configured categories."""
        commands = {name: self.get_command(ctx, name) for name in self.list_commands(ctx)}
        rendered: set[str] = set()

        for category, names in self.command_categories.items():
            rows: list[tuple[str, str]] = []
            for name in names:
                command = commands.get(name)
                if command is None or command.hidden:
                    continue
                rows.append((name, command.get_short_help_str()))
                rendered.add(name)
            if rows:
                with formatter.section(category):
                    formatter.write_dl(rows)

        remaining = [
            (name, command.get_short_help_str())
            for name, command in commands.items()
            if command is not None and not command.hidden and name not in rendered
        ]
        if remaining:
            with formatter.section("Other Commands"):
                formatter.write_dl(remaining)


@click.group(cls=CategorizedGroup)
@click.option(
    "--root",
    default=None,
    metavar="PATH",
    help="Path to the .zhar/ directory (default: auto-detect).",
)
@click.option(
    "--no-session",
    is_flag=True,
    help="Disable transient session tracking for this invocation.",
)
@click.pass_context
def cli(ctx: click.Context, root: str | None, no_session: bool) -> None:
    """zhar — project memory tool."""
    ctx.ensure_object(dict)
    ctx.obj["root"] = root
    ctx.obj["no_session"] = no_session


register_memory_commands(cli)
register_facts_commands(cli)
register_session_commands(cli)
register_install_commands(cli)
register_harness_commands(cli)
register_stack_commands(cli)
register_agent_commands(cli)