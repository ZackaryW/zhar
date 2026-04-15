"""CLI command group for transient session runtime helpers."""

from __future__ import annotations

import os

import click

from zhar.cli.serializers import render_json, session_current_to_payload
from zhar.mem_session.runtime import get_session_runtime, get_suspicious_node_ids, list_project_sessions
from zhar.mem_session.store import SESSION_DISABLED_ID, delete_session, load_session


@click.group(name="session")
@click.pass_context
def session_group(ctx: click.Context) -> None:
    """Inspect or adopt transient session runtime state."""


@session_group.command("list")
@click.pass_context
def session_list_command(ctx: click.Context) -> None:
    """List visible transient sessions, prioritizing the current project."""
    sessions = list_project_sessions(root=ctx.obj.get("root"))
    if not sessions:
        click.echo("(no sessions found)")
        return

    for session in sessions:
        suspicious = sum(1 for state in session.nodes.values() if state.status == "suspicious")
        cwd_text = session.cwd if session.cwd is not None else ""
        click.echo(
            f"{session.session_id}  project_root={session.project_root}  "
            f"cwd={cwd_text}  updated_at={session.updated_at}  suspicious={suspicious}"
        )


@session_group.command("adopt")
@click.argument("session_id")
def session_adopt_command(session_id: str) -> None:
    """Adopt *session_id* for the current zhar process only."""
    os.environ["ZHAR_SESSION_ID"] = session_id
    click.echo(f"Adopted session {session_id} for this process.")


@session_group.command("current")
@click.option("--format", "output_format", type=click.Choice(["text", "json"], case_sensitive=False), default="text", show_default=True, help="Render the output in text or JSON form.")
@click.pass_context
def session_current_command(ctx: click.Context, output_format: str) -> None:
    """Show the active transient session and its current recorded state."""
    runtime = get_session_runtime(ctx)
    session = load_session(runtime.session_id, base_dir=runtime.session_dir) if runtime.enabled else None
    shown_nodes = len(session.nodes) if session is not None else 0
    suspicious_nodes = (
        sum(1 for state in session.nodes.values() if state.status == "suspicious")
        if session is not None else 0
    )
    if output_format == "json":
        click.echo(render_json(session_current_to_payload(
            session_id=runtime.session_id,
            enabled=runtime.enabled,
            project_root=str(runtime.project_root),
            session_dir=str(runtime.session_dir),
            shown_nodes=shown_nodes,
            suspicious_nodes=suspicious_nodes,
            challenge_enabled=runtime.challenge_enabled,
            challenge_agent=runtime.challenge_agent,
        )))
        return
    click.echo(f"session_id={runtime.session_id}")
    click.echo(f"enabled={str(runtime.enabled).lower()}")
    click.echo(f"project_root={runtime.project_root}")
    click.echo(f"session_dir={runtime.session_dir}")
    click.echo(f"shown_nodes={shown_nodes}")
    click.echo(f"suspicious_nodes={suspicious_nodes}")
    click.echo(f"challenge_enabled={str(runtime.challenge_enabled).lower()}")
    if runtime.challenge_agent:
        click.echo(f"challenge_agent={runtime.challenge_agent}")


@session_group.command("clear")
@click.pass_context
def session_clear_command(ctx: click.Context) -> None:
    """Delete the currently active transient session file when present."""
    runtime = get_session_runtime(ctx)
    if not runtime.enabled or runtime.session_id == SESSION_DISABLED_ID:
        click.echo("Session tracking is disabled.")
        return
    deleted = delete_session(runtime.session_id, base_dir=runtime.session_dir)
    if deleted:
        click.echo(f"Cleared session {runtime.session_id}.")
        return
    click.echo(f"No session file found for {runtime.session_id}.")


@session_group.command("need-challenge")
@click.pass_context
def session_need_challenge_command(ctx: click.Context) -> None:
    """Print suspicious node IDs when challenge reporting is currently enabled."""
    runtime = get_session_runtime(ctx)
    if runtime.session_id == SESSION_DISABLED_ID or not runtime.challenge_enabled:
        click.echo("No suspicious nodes.")
        return

    node_ids = get_suspicious_node_ids(runtime)
    if not node_ids:
        click.echo("No suspicious nodes.")
        return

    if runtime.challenge_agent:
        click.echo(f"challenge_agent={runtime.challenge_agent}")
    for node_id in node_ids:
        click.echo(node_id)


def register_session_commands(cli_group: click.Group) -> None:
    """Register the transient session command group on *cli_group*."""
    cli_group.add_command(session_group)