"""Filesystem helpers for transient session documents."""

from __future__ import annotations

import tempfile
from pathlib import Path

import orjson

from zhar.mem_session.model import SessionData

SESSION_DISABLED_ID = "00000000"


def default_session_dir() -> Path:
    """Return the temp-directory location used for transient session files."""
    return Path(tempfile.gettempdir()) / "zhar_cache" / "session"


def session_file_path(session_id: str, *, base_dir: Path | None = None) -> Path:
    """Return the transient session file path for *session_id*."""
    return (base_dir if base_dir is not None else default_session_dir()) / f"{session_id}.json"


def load_session(session_id: str, *, base_dir: Path | None = None) -> SessionData | None:
    """Load one session document when it exists, else return ``None``."""
    path = session_file_path(session_id, base_dir=base_dir)
    if not path.exists():
        return None
    raw = path.read_bytes()
    if not raw.strip():
        return None
    return SessionData.from_dict(orjson.loads(raw))


def save_session(session: SessionData, *, base_dir: Path | None = None) -> Path:
    """Persist *session* and return the written path."""
    path = session_file_path(session.session_id, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(session.to_dict(), option=orjson.OPT_INDENT_2))
    return path


def delete_session(session_id: str, *, base_dir: Path | None = None) -> bool:
    """Delete the transient session file for *session_id* when it exists."""
    path = session_file_path(session_id, base_dir=base_dir)
    if not path.exists():
        return False
    path.unlink()
    return True


def list_sessions(*, base_dir: Path | None = None) -> list[SessionData]:
    """Return all readable transient session documents from the session directory."""
    session_dir = base_dir if base_dir is not None else default_session_dir()
    if not session_dir.exists():
        return []

    sessions: list[SessionData] = []
    for path in sorted(session_dir.glob("*.json")):
        try:
            loaded = load_session(path.stem, base_dir=session_dir)
        except orjson.JSONDecodeError:
            continue
        if loaded is not None:
            sessions.append(loaded)
    return sessions