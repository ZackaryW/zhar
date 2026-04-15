# Session Runtime Spec

## Status

Draft design spec. Phase 1 implemented.

Implemented in phase 1:

- transient session storage under the OS temp directory
- root-level `--no-session` support
- `show` tracking for shallow and relation-expanded inspection
- runtime export session block when runtime context is requested
- `zhar session list`, `zhar session adopt`, and `zhar session need-challenge`
- `zhar session current` and `zhar session clear`
- fact-gated challenge reporting via `session_challenge_enabled` and `session_challenge_agent`

Operational note:

- CLI body staging uses environment variables, not shell-local variables. In PowerShell, use `$env:ZHAR_NOTE_BODY = ...` with `--from-env ZHAR_NOTE_BODY` or `--content-var ZHAR_NOTE_BODY`.

## Goal

Add a transient session subsystem to zhar that tracks node inspection behavior during CLI usage and surfaces challenge pressure through runtime export context without polluting durable project memory.

## Non-Goals

- Do not store session state under `.zhar/mem/`.
- Do not write challenge state into durable `notes` or other memory groups.
- Do not make subagent invocation mandatory inside zhar itself.

## Scope

The session subsystem applies to CLI-driven runtime behavior such as `show` and `export`.

It introduces:

- session identity resolution for the current CLI process
- transient per-node session state in the OS temp directory
- challenge-pressure scoring based on repeated inspection without sufficient expansion
- runtime export context that reports suspicious nodes
- a repo-local challenge agent contract that host agents may invoke

## Design Principles

1. Session data is runtime state, not durable memory.
2. The session must work with ordinary Click CLI process behavior.
3. Session-aware features must be fully disabled when the reserved sentinel session ID is active.
4. Export may report challenge state, but zhar itself should not force subagent execution.
5. Suspicion should be deterministic and easy to test.

## Session Identity

### Resolution Model

At the start of each CLI invocation, resolve the active session ID in this order:

1. If `--no-session` is present, use the reserved sentinel `00000000`.
2. Else if `ZHAR_SESSION_ID` exists in the current process environment, use it.
3. Else generate a UUID4 string, assign it to `os.environ["ZHAR_SESSION_ID"]`, and use it for the rest of the current CLI process.

### Important Behavior

Assigning `os.environ["ZHAR_SESSION_ID"]` only affects the current zhar process and any subprocesses it spawns. It does not persist into the parent shell automatically.

That is acceptable for this design because zhar also provides explicit session adoption commands so operators or host environments can reuse a chosen session ID intentionally.

### Sentinel Session

The reserved session ID `00000000` means session features are disabled.

When the sentinel is active:

- no session file is created
- no show-state tracking is written
- no challenge score is computed
- export omits session challenge context

## Storage Layout

### Location

Store session files under:

```text
{temp}/zhar_cache/session/{session-id}.json
```

### Directory Rules

- Create the directory lazily on first session write.
- Treat files there as disposable runtime artifacts.
- Do not commit them to source control.
- Session listing should group visible session files by recorded project root / current working directory.

## Session File Schema

```json
{
  "session_id": "f81d4fae-7dec-11d0-a765-00a0c91e6bf6",
  "project_root": "D:/zhar",
  "started_at": "2026-04-15T18:30:00Z",
  "updated_at": "2026-04-15T18:31:00Z",
  "nodes": {
    "353ca": {
      "state": "shown",
      "show_count": 3,
      "expanded_count": 1,
      "last_shown_at": "2026-04-15T18:30:40Z",
      "last_expanded_at": "2026-04-15T18:30:10Z",
      "score": 12,
      "status": "normal"
    }
  }
}
```

Additional optional top-level fields may include:

- `cwd`: recorded current working directory for session listing and adoption UX
- `challenge_enabled`: cached resolved flag derived from effective facts

## Node Session State

### States

- `unknown`: no session interaction recorded
- `shown`: node was shown but not fully expanded
- `expanded`: node was shown in a way that qualifies as full expansion
- `suspicious`: computed score exceeded the challenge threshold

### Fully Expanded Definition

For the first implementation, a node counts as fully expanded only when:

- `show --relation-depth N` is invoked with `N > 0`

Plain `show <id>` does not count as fully expanded.

This definition may be extended later if zhar adds richer expansion modes such as note-depth or explicit full expansion flags.

## Scoring Model

This subsystem uses challenge pressure, not decay.

### Inputs

- every plain show adds `1`
- every 20 seconds since the last full expansion adds `1`
- every fully expanded show resets the node score to `0`

### Threshold

When a node's score becomes greater than `50`, its session status becomes `suspicious`.

### Interpretation

The score is intended to catch repeated shallow inspection of the same node without meaningful re-expansion.

## Event Semantics

### Plain Show

Example:

```text
zhar show 353ca
```

Effects:

- update `last_shown_at`
- increment `show_count`
- set state to `shown` unless already `suspicious`
- recompute score

### Expanded Show

Example:

```text
zhar show 353ca --relation-depth 1
```

Effects:

- update `last_shown_at`
- update `last_expanded_at`
- increment `expanded_count`
- set state to `expanded`
- reset score to `0`
- clear `suspicious` status

## Export Runtime Context

### Purpose

`zhar export` should surface current session inspection state and challenge pressure as runtime context for agents.

This is runtime-only output and must not be written into durable memory groups.

### Suggested Output Block

```text
### Session state
session_id=f81d4fae-7dec-11d0-a765-00a0c91e6bf6
shown_nodes=2
suspicious_nodes=2
challenge_enabled=true

- 217d3 state=shown score=17
- 353ca score=57 state=suspicious
- 393df score=61 state=suspicious
```

### Inclusion Rule

Only include this block when:

- session features are enabled
- at least one node has recorded session state

### Need-Challenge Surface

Add a dedicated command:

```text
zhar session need-challenge
```

Behavior:

- exits successfully with a list of suspicious node IDs when challenge is needed
- prints no results when no node is suspicious
- honors the challenge enablement fact described below

## Challenge Workflow

### Trigger

When export runtime context reports suspicious nodes and challenge is enabled, the host agent should treat that as a challenge request.

### Resolution Options

The host agent may:

1. Re-expand the node via `show --relation-depth > 0`, which resets the score.
2. Invoke a repo-local challenge subagent.

### Challenge Agent Contract

Add a repo-local agent file under:

```text
.github/agents/challenge-judge.agent.md
```

Responsibilities:

- receive the suspicious node IDs and session context
- run `show` checks for each node
- summarize whether the primary agent adequately inspected the nodes
- return a concise pass/fail assessment with rationale

### Boundary

zhar should expose the challenge requirement and recommended agent name. The host agent runtime is responsible for deciding whether to invoke the subagent.

## Facts Integration

Challenge behavior should be fact-driven.

Suggested effective facts:

- `session_challenge_enabled=true|false`
- `session_challenge_agent=challenge-judge`

Behavior:

- if `session_challenge_enabled` is false or unset, zhar may still track session state but should not surface challenge-required runtime output
- if `session_challenge_enabled` is true, export and `zhar session need-challenge` should expose suspicious nodes
- if `session_challenge_agent` is set, export should report that agent name in runtime context

## CLI Surface Proposal

### Global Session Flag

Add a root-level Click option:

```text
--no-session
```

This should apply to all CLI commands in the current invocation.

### Optional Session Commands

Phase 1 session commands should include:

- `zhar session list`
- `zhar session adopt <session-id>`
- `zhar session need-challenge`

Later commands may include:

- `zhar session inspect`

### Session List

`zhar session list` should enumerate active session files and include:

- session ID
- recorded project root
- recorded cwd
- last updated time
- suspicious node count

The default presentation should make it easy to see sessions relevant to the current working directory first.

### Session Adopt

`zhar session adopt <session-id>` should make the given session ID the active session for the running CLI process by assigning it into `os.environ["ZHAR_SESSION_ID"]`.

This does not retroactively change the parent shell environment, but it gives host tools and wrapper commands an explicit surface to reuse a known session.

## Module Structure Proposal

Suggested new modules:

```text
src/zhar/mem_session/__init__.py
src/zhar/mem_session/model.py
src/zhar/mem_session/store.py
src/zhar/mem_session/runtime.py
src/zhar/mem_session/scoring.py
```

Responsibilities:

- `model.py`: typed session dataclasses
- `store.py`: temp-file load/save helpers
- `runtime.py`: session ID resolution and disabled sentinel handling
- `scoring.py`: deterministic score/status computation

## Integration Points

### CLI bootstrap

The top-level CLI should resolve session state once per invocation and make it available through `ctx.obj`.

### Show

`show` should emit normal node output and update session state according to whether the show was plain or expanded.

### Export

`export` should read the active session state and append the session runtime block when nodes have recorded state.

When challenge is fact-enabled, export should additionally surface suspicious nodes as challenge-required state.

### Agent get and stack sync

Phase 1 should not modify `agent get` or `stack sync` behavior directly.

If later desired, export consumers may indirectly surface session runtime context when they consume export output.

## Testing Plan

### Unit Tests

- session ID resolution with existing env var
- session ID generation when env var missing
- sentinel disable behavior for `--no-session`
- session adopt updates the active process environment
- session list groups or filters by cwd/project root record
- score progression over elapsed time
- score reset on expanded show
- suspicious threshold transition
- challenge enablement fact gating

### Integration Tests

- `show` writes session file updates
- `show --relation-depth` resets node score
- export includes session runtime block when nodes are shown
- export includes challenge-required output only when suspicious nodes exist and challenge is fact-enabled
- `zhar session need-challenge` reports suspicious nodes correctly
- `zhar session list` reports active sessions for the current cwd

## Rollout Phases

### Phase 1

- session ID resolution per CLI invocation
- transient temp-file storage
- `show` state updates
- scoring engine
- `session list`, `session adopt`, and `session need-challenge`
- export runtime session block
- fact-gated challenge block

### Phase 2

- challenge judge agent file
- optional session inspection commands
- richer expansion definitions beyond relation-depth

### Phase 3

- component-aware expansion across non-relation node types once shared component identity exists

## Open Questions

1. Should session list hide stale temp sessions by default or show all until explicitly cleared?
2. Should expanded state eventually include note-depth or other future expansion modes?
3. Should suspicious-node reporting be capped or sorted by score in export output?
4. Should challenge enablement default to false unless `session_challenge_enabled=true` is present in effective facts?