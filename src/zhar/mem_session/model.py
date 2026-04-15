"""Serializable transient session data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SessionNodeState:
    """Transient inspection state for a single memory node within one session."""

    state: str = "unknown"
    show_count: int = 0
    expanded_count: int = 0
    last_shown_at: str | None = None
    last_expanded_at: str | None = None
    last_scored_at: str | None = None
    score: int = 0
    status: str = "normal"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping for this node state."""
        data: dict[str, Any] = {
            "state": self.state,
            "show_count": self.show_count,
            "expanded_count": self.expanded_count,
            "score": self.score,
            "status": self.status,
        }
        if self.last_shown_at is not None:
            data["last_shown_at"] = self.last_shown_at
        if self.last_expanded_at is not None:
            data["last_expanded_at"] = self.last_expanded_at
        if self.last_scored_at is not None:
            data["last_scored_at"] = self.last_scored_at
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionNodeState:
        """Build a node state from a persisted mapping."""
        return cls(
            state=str(data.get("state", "unknown")),
            show_count=int(data.get("show_count", 0)),
            expanded_count=int(data.get("expanded_count", 0)),
            last_shown_at=_maybe_string(data.get("last_shown_at")),
            last_expanded_at=_maybe_string(data.get("last_expanded_at")),
            last_scored_at=_maybe_string(data.get("last_scored_at")),
            score=int(data.get("score", 0)),
            status=str(data.get("status", "normal")),
        )


@dataclass(slots=True)
class SessionData:
    """Persisted transient session document stored in the temp session directory."""

    session_id: str
    project_root: str
    started_at: str
    updated_at: str
    nodes: dict[str, SessionNodeState] = field(default_factory=dict)
    cwd: str | None = None
    challenge_enabled: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable mapping for the session document."""
        data: dict[str, Any] = {
            "session_id": self.session_id,
            "project_root": self.project_root,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "nodes": {node_id: state.to_dict() for node_id, state in self.nodes.items()},
        }
        if self.cwd is not None:
            data["cwd"] = self.cwd
        if self.challenge_enabled is not None:
            data["challenge_enabled"] = self.challenge_enabled
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionData:
        """Build a session document from a persisted mapping."""
        raw_nodes = data.get("nodes", {})
        node_map = {
            str(node_id): SessionNodeState.from_dict(state)
            for node_id, state in dict(raw_nodes).items()
        }
        challenge_enabled = data.get("challenge_enabled")
        parsed_challenge = None if challenge_enabled is None else bool(challenge_enabled)
        return cls(
            session_id=str(data["session_id"]),
            project_root=str(data["project_root"]),
            started_at=str(data["started_at"]),
            updated_at=str(data["updated_at"]),
            nodes=node_map,
            cwd=_maybe_string(data.get("cwd")),
            challenge_enabled=parsed_challenge,
        )


def _maybe_string(value: Any) -> str | None:
    """Return *value* as a string when present, else ``None``."""
    if value is None:
        return None
    return str(value)