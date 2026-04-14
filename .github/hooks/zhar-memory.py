"""Workspace hook that enforces zhar memory refreshes around mutating work."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

ZHAR_LAUNCHERS = (
    "zhar",
    "uv run zhar",
    "uvx zhar",
    "pipx run zhar",
)

READ_SUBCOMMANDS = (
    "export",
    "status",
    "show",
    "query",
    "facts list",
)

UPDATE_SUBCOMMANDS = (
    "add",
    "note",
    "facts set",
    "facts unset",
    "scan",
    "verify",
    "gc",
)

PREFLIGHT_EXAMPLES = "zhar export, uv run zhar export, uvx zhar export, or pipx run zhar export"
STATUS_EXAMPLES = "zhar status, uv run zhar status, uvx zhar status, or pipx run zhar status"
UPDATE_EXAMPLES = (
    "zhar add/note/facts set/scan, uv run zhar add/note/facts set/scan, "
    "uvx zhar add/note/facts set/scan, or pipx run zhar add/note/facts set/scan"
)

READ_ONLY_TOOLS = {
    "read",
    "search",
    "file_search",
    "grep_search",
    "list_dir",
    "semantic_search",
    "get_errors",
    "manage_todo_list",
    "todo",
}


@dataclass
class HookState:
    """Track whether preflight and post-change memory updates are pending."""

    awaiting_preflight: bool = True
    awaiting_post_update: bool = False


def load_payload(raw: str) -> dict[str, Any]:
    """Parse a hook payload from standard input."""
    data = raw.strip()
    if not data:
        return {}
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def state_path(workspace_root: Path) -> Path:
    """Return the transient state file used to coordinate hook decisions."""
    git_dir = workspace_root / ".git"
    if git_dir.exists():
        return git_dir / "zhar-memory-hook-state.json"
    return workspace_root / ".github" / "hooks" / ".zhar-memory-hook-state.json"


def load_state(workspace_root: Path) -> HookState:
    """Load the current hook state for the workspace."""
    path = state_path(workspace_root)
    if not path.exists():
        return HookState()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return HookState()
    if not isinstance(payload, dict):
        return HookState()
    return HookState(
        awaiting_preflight=bool(payload.get("awaiting_preflight", True)),
        awaiting_post_update=bool(payload.get("awaiting_post_update", False)),
    )


def save_state(workspace_root: Path, state: HookState) -> None:
    """Persist the current hook state for the workspace."""
    path = state_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "awaiting_preflight": state.awaiting_preflight,
                "awaiting_post_update": state.awaiting_post_update,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def detect_event(payload: dict[str, Any]) -> str | None:
    """Extract the hook event name from a payload."""
    for key in ("hookEventName", "eventName", "event"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return None


def detect_tool_name(payload: dict[str, Any]) -> str | None:
    """Extract the tool name from a hook payload when present."""
    for key in ("toolName", "tool_name", "tool"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested_name = value.get("name")
            if isinstance(nested_name, str):
                return nested_name
    return None


def detect_command_text(payload: dict[str, Any]) -> str:
    """Extract a shell command string from the payload when present."""
    candidates: list[Any] = [
        payload.get("command"),
        payload.get("input"),
        payload.get("toolInput"),
        payload.get("arguments"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str):
            return candidate
        if isinstance(candidate, dict):
            for key in ("command", "input", "text"):
                nested = candidate.get(key)
                if isinstance(nested, str):
                    return nested
    return ""


def _matches_zhar_command(command: str, subcommand: str) -> bool:
    """Return whether *command* starts with any supported zhar launcher + subcommand."""
    return any(command.startswith(f"{launcher} {subcommand}") for launcher in ZHAR_LAUNCHERS)


def is_memory_read_command(command: str) -> bool:
    """Return whether *command* refreshes zhar memory context."""
    return any(_matches_zhar_command(command, subcommand) for subcommand in READ_SUBCOMMANDS)


def is_memory_update_command(command: str) -> bool:
    """Return whether *command* records or validates zhar memory updates."""
    return any(_matches_zhar_command(command, subcommand) for subcommand in UPDATE_SUBCOMMANDS)


def is_mutating_tool(tool_name: str | None, command: str) -> bool:
    """Return whether the tool invocation changes workspace state."""
    if tool_name in READ_ONLY_TOOLS:
        return False
    if command and (is_memory_read_command(command) or is_memory_update_command(command)):
        return False
    if tool_name is None:
        return bool(command)
    return True


def permission_response(reason: str, message: str) -> dict[str, Any]:
    """Build a blocking PreToolUse response."""
    return {
        "systemMessage": message,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
    }


def message_response(message: str) -> dict[str, Any]:
    """Build a hook response that only emits a system message."""
    return {"systemMessage": message}


def handle_event(payload: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    """Evaluate a hook event and return the hook response."""
    event = detect_event(payload)
    state = load_state(workspace_root)
    tool_name = detect_tool_name(payload)
    command = detect_command_text(payload).strip()

    if event == "UserPromptSubmit":
        state.awaiting_preflight = True
        save_state(workspace_root, state)
        return message_response(
            f"Before mutating work, refresh memory with {PREFLIGHT_EXAMPLES} or {STATUS_EXAMPLES}."
        )

    if event == "PreToolUse":
        if command and is_memory_read_command(command):
            return {}
        if state.awaiting_preflight and is_mutating_tool(tool_name, command):
            return permission_response(
                "zhar memory preflight is required before mutating work.",
                f"Run {PREFLIGHT_EXAMPLES} or {STATUS_EXAMPLES} before editing files or running mutating commands.",
            )
        if state.awaiting_post_update and is_mutating_tool(tool_name, command):
            return permission_response(
                "zhar memory must be updated after mutating work.",
                f"Update memory with {UPDATE_EXAMPLES}, then validate with zhar verify/gc or your equivalent launcher.",
            )
        return {}

    if event == "PostToolUse":
        if command and is_memory_read_command(command):
            state.awaiting_preflight = False
            save_state(workspace_root, state)
            return message_response("zhar memory preflight recorded.")
        if command and is_memory_update_command(command):
            state.awaiting_post_update = False
            save_state(workspace_root, state)
            return message_response("zhar memory update recorded.")
        if is_mutating_tool(tool_name, command):
            state.awaiting_post_update = True
            save_state(workspace_root, state)
            return message_response(
                f"Workspace changed. Update zhar memory before continuing: use {UPDATE_EXAMPLES}, then validate with zhar verify or your equivalent launcher."
            )
        return {}

    if event == "Stop" and state.awaiting_post_update:
        return message_response(
            f"Session ended while zhar memory was still stale. Record the change with {UPDATE_EXAMPLES}, then validate."
        )

    return {}


def main() -> None:
    """Run the workspace hook entrypoint."""
    payload = load_payload(sys.stdin.read())
    response = handle_event(payload, Path.cwd())
    if response:
        sys.stdout.write(json.dumps(response))


if __name__ == "__main__":
    main()