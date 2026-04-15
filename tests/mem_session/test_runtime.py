"""TDD: transient session runtime state and scoring."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from zhar.mem_session.model import SessionData, SessionNodeState
from zhar.mem_session.runtime import (
    SessionRuntime,
    format_session_runtime_block,
    get_suspicious_node_ids,
    record_show_event,
)
from zhar.mem_session.store import default_session_dir, load_session, save_session
from zhar.utils.times import format_dt


def _runtime(tmp_path, *, challenge_enabled: bool = False, challenge_agent: str | None = None) -> SessionRuntime:
    """Return a session runtime bound to a temporary session directory."""
    return SessionRuntime(
        session_id="session-one",
        enabled=True,
        project_root=tmp_path,
        cwd=tmp_path,
        challenge_enabled=challenge_enabled,
        challenge_agent=challenge_agent,
        session_dir=tmp_path / "sessions",
    )


class TestRecordShowEvent:
    def test_plain_show_marks_node_shown_and_increments_score(self, tmp_path) -> None:
        """A plain show should create transient state and start scoring at one."""
        runtime = _runtime(tmp_path)
        now = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)

        record_show_event(runtime, "353ca", relation_depth=0, now=now)

        session = load_session(runtime.session_id, base_dir=runtime.session_dir)
        assert session is not None
        state = session.nodes["353ca"]
        assert state.state == "shown"
        assert state.show_count == 1
        assert state.expanded_count == 0
        assert state.score == 1
        assert state.status == "normal"

    def test_plain_show_accumulates_time_pressure_without_double_counting(self, tmp_path) -> None:
        """Time pressure should be added once per elapsed twenty-second bucket."""
        runtime = _runtime(tmp_path)
        start = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)

        record_show_event(runtime, "353ca", relation_depth=0, now=start)
        record_show_event(runtime, "353ca", relation_depth=0, now=start + timedelta(seconds=61))

        session = load_session(runtime.session_id, base_dir=runtime.session_dir)
        assert session is not None
        state = session.nodes["353ca"]
        assert state.score == 5
        assert state.state == "shown"

    def test_expanded_show_resets_score_and_marks_node_expanded(self, tmp_path) -> None:
        """A relation-expanded show should clear challenge pressure for the node."""
        runtime = _runtime(tmp_path)
        start = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)

        record_show_event(runtime, "353ca", relation_depth=0, now=start)
        record_show_event(runtime, "353ca", relation_depth=1, now=start + timedelta(seconds=5))

        session = load_session(runtime.session_id, base_dir=runtime.session_dir)
        assert session is not None
        state = session.nodes["353ca"]
        assert state.state == "expanded"
        assert state.show_count == 2
        assert state.expanded_count == 1
        assert state.score == 0
        assert state.status == "normal"


class TestRuntimeContext:
    def test_runtime_block_reports_recorded_show_state(self, tmp_path) -> None:
        """Runtime export context should surface the current transient session state."""
        runtime = _runtime(tmp_path)
        now = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)

        record_show_event(runtime, "353ca", relation_depth=0, now=now)

        block = format_session_runtime_block(runtime)

        assert block is not None
        assert "### Session state" in block
        assert "session_id=session-one" in block
        assert "shown_nodes=1" in block
        assert "challenge_enabled=false" in block
        assert "- 353ca state=shown score=1" in block

    def test_suspicious_nodes_are_reported_only_when_challenge_is_enabled(self, tmp_path) -> None:
        """Challenge queries should stay fact-gated even when suspicion was recorded."""
        runtime = _runtime(tmp_path, challenge_enabled=True, challenge_agent="challenge-judge")
        start = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)

        record_show_event(runtime, "353ca", relation_depth=0, now=start)
        record_show_event(runtime, "353ca", relation_depth=0, now=start + timedelta(seconds=1001))

        assert get_suspicious_node_ids(runtime) == ["353ca"]

        disabled_runtime = replace(runtime, challenge_enabled=False)
        assert get_suspicious_node_ids(disabled_runtime) == []

        block = format_session_runtime_block(runtime)
        assert block is not None
        assert "suspicious_nodes=1" in block
        assert "challenge_agent=challenge-judge" in block


class TestStore:
    def test_default_session_dir_uses_zhar_cache_root(self, monkeypatch, tmp_path) -> None:
        """Default temp session storage should live under zhar_cache/session."""
        monkeypatch.setattr("zhar.mem_session.store.tempfile.gettempdir", lambda: str(tmp_path))

        assert default_session_dir() == tmp_path / "zhar_cache" / "session"

    def test_save_and_load_round_trip_session_payload(self, tmp_path) -> None:
        """Session store should preserve the serialized node state structure."""
        now = datetime(2026, 4, 15, 18, 30, tzinfo=timezone.utc)
        session = SessionData(
            session_id="session-one",
            project_root=str(tmp_path),
            cwd=str(tmp_path),
            started_at=format_dt(now),
            updated_at=format_dt(now),
            nodes={
                "353ca": SessionNodeState(
                    state="suspicious",
                    show_count=7,
                    expanded_count=1,
                    last_shown_at=format_dt(now),
                    last_expanded_at=format_dt(now),
                    last_scored_at=format_dt(now),
                    score=57,
                    status="suspicious",
                )
            },
        )

        save_session(session, base_dir=tmp_path / "sessions")

        loaded = load_session("session-one", base_dir=tmp_path / "sessions")
        assert loaded == session