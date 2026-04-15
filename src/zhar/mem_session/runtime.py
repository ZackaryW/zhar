"""Session runtime resolution, scoring, and export formatting."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import click

from zhar.mem_session.model import SessionData, SessionNodeState
from zhar.mem_session.store import SESSION_DISABLED_ID, default_session_dir, load_session, save_session
from zhar.utils.config import find_zhar_root
from zhar.utils.facts import load_effective_facts, project_facts_path
from zhar.utils.times import format_dt, parse_dt, utcnow

_CHALLENGE_ENABLED_FACT = "session_challenge_enabled"
_CHALLENGE_AGENT_FACT = "session_challenge_agent"
_SCORE_INTERVAL_SECONDS = 20
_SUSPICIOUS_THRESHOLD = 50


@dataclass(slots=True)
class SessionRuntime:
    """Resolved session runtime settings for one CLI invocation."""

    session_id: str
    enabled: bool
    project_root: Path
    cwd: Path
    challenge_enabled: bool
    challenge_agent: str | None
    session_dir: Path


def get_session_runtime(ctx: click.Context) -> SessionRuntime:
    """Return the lazily resolved session runtime stored on the Click context."""
    runtime = ctx.obj.get("session_runtime")
    if runtime is None:
        runtime = resolve_session_runtime(
            root=ctx.obj.get("root"),
            no_session=bool(ctx.obj.get("no_session", False)),
        )
        ctx.obj["session_runtime"] = runtime
    return runtime


def resolve_session_runtime(
    *,
    root: str | None,
    no_session: bool,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    session_dir: Path | None = None,
) -> SessionRuntime:
    """Resolve the active session identity and effective challenge settings."""
    resolved_cwd = cwd if cwd is not None else Path.cwd()
    zhar_root = _resolve_zhar_root(root, resolved_cwd)
    project_root = zhar_root.parent
    effective_facts = load_effective_facts(project_facts_path(zhar_root))
    challenge_enabled = _fact_is_true(effective_facts.get(_CHALLENGE_ENABLED_FACT))
    challenge_agent = effective_facts.get(_CHALLENGE_AGENT_FACT)
    target_env = env if env is not None else os.environ
    runtime_session_dir = session_dir if session_dir is not None else default_session_dir()

    if no_session:
        return SessionRuntime(
            session_id=SESSION_DISABLED_ID,
            enabled=False,
            project_root=project_root,
            cwd=resolved_cwd,
            challenge_enabled=False,
            challenge_agent=None,
            session_dir=runtime_session_dir,
        )

    session_id = target_env.get("ZHAR_SESSION_ID")
    if not session_id:
        session_id = str(uuid4())
        target_env["ZHAR_SESSION_ID"] = session_id

    return SessionRuntime(
        session_id=session_id,
        enabled=session_id != SESSION_DISABLED_ID,
        project_root=project_root,
        cwd=resolved_cwd,
        challenge_enabled=challenge_enabled,
        challenge_agent=challenge_agent,
        session_dir=runtime_session_dir,
    )


def record_show_event(
    runtime: SessionRuntime,
    node_id: str,
    *,
    relation_depth: int,
    now: datetime | None = None,
) -> None:
    """Record one show event for *node_id* in the active transient session."""
    if not runtime.enabled:
        return

    moment = now if now is not None else utcnow()
    session = _load_or_create_session(runtime, moment)
    state = session.nodes.get(node_id, SessionNodeState())
    state.show_count += 1
    state.last_shown_at = format_dt(moment)

    if relation_depth > 0:
        state.expanded_count += 1
        state.last_expanded_at = format_dt(moment)
        state.last_scored_at = format_dt(moment)
        state.score = 0
        state.state = "expanded"
        state.status = "normal"
    else:
        state.score = _next_plain_show_score(session, state, moment)
        state.last_scored_at = format_dt(moment)
        if state.score > _SUSPICIOUS_THRESHOLD:
            state.state = "suspicious"
            state.status = "suspicious"
        else:
            state.state = "shown"
            state.status = "normal"

    session.nodes[node_id] = state
    session.updated_at = format_dt(moment)
    session.cwd = str(runtime.cwd)
    session.project_root = str(runtime.project_root)
    session.challenge_enabled = runtime.challenge_enabled
    save_session(session, base_dir=runtime.session_dir)


def format_session_runtime_block(runtime: SessionRuntime) -> str | None:
    """Return the export-time session block when transient state exists."""
    if not runtime.enabled:
        return None
    session = load_session(runtime.session_id, base_dir=runtime.session_dir)
    if session is None or not session.nodes:
        return None

    suspicious_ids = [node_id for node_id, state in session.nodes.items() if state.status == "suspicious"]
    lines = [
        "### Session state",
        f"session_id={runtime.session_id}",
        f"shown_nodes={len(session.nodes)}",
        f"suspicious_nodes={len(suspicious_ids)}",
        f"challenge_enabled={str(runtime.challenge_enabled).lower()}",
    ]
    if runtime.challenge_enabled and runtime.challenge_agent:
        lines.append(f"challenge_agent={runtime.challenge_agent}")
    lines.append("")
    for node_id, state in sorted(session.nodes.items()):
        lines.append(f"- {node_id} state={state.state} score={state.score}")
    return "\n".join(lines)


def get_suspicious_node_ids(runtime: SessionRuntime) -> list[str]:
    """Return suspicious node IDs only when challenge reporting is enabled."""
    if not runtime.enabled or not runtime.challenge_enabled:
        return []
    session = load_session(runtime.session_id, base_dir=runtime.session_dir)
    if session is None:
        return []
    return sorted(node_id for node_id, state in session.nodes.items() if state.status == "suspicious")


def list_project_sessions(*, root: str | None, cwd: Path | None = None) -> list[SessionData]:
    """Return transient sessions ordered with the current project sessions first."""
    resolved_cwd = cwd if cwd is not None else Path.cwd()
    project_root = _resolve_zhar_root(root, resolved_cwd).parent
    sessions = load_all_sessions()
    return sorted(
        sessions,
        key=lambda session: (
            session.project_root != str(project_root),
            session.cwd != str(resolved_cwd),
            session.updated_at,
        ),
        reverse=False,
    )


def load_all_sessions() -> list[SessionData]:
    """Return all transient session documents visible from the default session directory."""
    from zhar.mem_session.store import list_sessions

    return list_sessions(base_dir=default_session_dir())


def _resolve_zhar_root(root: str | None, cwd: Path) -> Path:
    """Return the effective zhar root for the current CLI context."""
    if root:
        return Path(root)
    found = find_zhar_root(cwd)
    return found if found is not None else cwd / ".zhar"


def _load_or_create_session(runtime: SessionRuntime, now: datetime) -> SessionData:
    """Return the current session document, creating an empty one when needed."""
    loaded = load_session(runtime.session_id, base_dir=runtime.session_dir)
    if loaded is not None:
        return loaded
    timestamp = format_dt(now)
    return SessionData(
        session_id=runtime.session_id,
        project_root=str(runtime.project_root),
        cwd=str(runtime.cwd),
        started_at=timestamp,
        updated_at=timestamp,
        nodes={},
        challenge_enabled=runtime.challenge_enabled,
    )


def _next_plain_show_score(session: SessionData, state: SessionNodeState, now: datetime) -> int:
    """Return the next deterministic challenge score for a shallow show event."""
    reference = parse_dt(state.last_expanded_at) if state.last_expanded_at else parse_dt(session.started_at)
    prior_checkpoint = parse_dt(state.last_scored_at) if state.last_scored_at else reference
    elapsed_steps = max(0, int((now - reference).total_seconds() // _SCORE_INTERVAL_SECONDS))
    prior_steps = max(0, int((prior_checkpoint - reference).total_seconds() // _SCORE_INTERVAL_SECONDS))
    return state.score + 1 + max(0, elapsed_steps - prior_steps)


def _fact_is_true(value: str | None) -> bool:
    """Return whether a fact string should be interpreted as true."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}