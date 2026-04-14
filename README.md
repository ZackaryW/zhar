# zhar

zhar is an agent harness — a toolkit that provides all the scaffolding needed to make other agent tools successful in your codebase.

It goes beyond memory. zhar gives AI agents a persistent, structured foundation: durable project context they can read and write, a facts-driven template engine for generating skills and instructions, a versioned bucket system for distributing agent files, and lifecycle utilities (GC, verify, scan, export) that keep everything consistent across sessions, handoffs, and model resets.

At its core it gives you a checked-in `.zhar/` directory where AI agents and developers maintain:

- stable project goals and requirements
- active issues and blockers
- architecture decisions and research findings
- code-history notes linked to real source files
- supplemental notes attached to primary nodes when extra detail should stay out of normal exports

On top of memory, the stack system lets agent tools pull skills, instructions, agents, and hooks from versioned GitHub source buckets, render them against live project facts, and write them to whatever output directory the consuming tool expects.

---

## Table of Contents

1. [What zhar Does](#what-zhar-does)
2. [Quick Start](#quick-start)
3. [Memory Groups](#memory-groups)
4. [Daily Workflow](#daily-workflow)
5. [Source Markers](#source-markers)
6. [Facts](#facts)
7. [Stack: Skills, Instructions, and Agents](#stack-skills-instructions-and-agents)
8. [Source Bucket Shape](#source-bucket-shape)
9. [Extending zhar](#extending-zhar)

---

## What zhar Does

### Core purpose

zhar gives agent tools the foundation they need to operate successfully in a long-lived codebase. It answers the questions that ephemeral context cannot:

- what are the non-negotiable constraints for this codebase?
- why was this architectural choice made?
- what is actively broken or blocked?
- what must an agent not change?
- which skills and instructions should be active for this project right now?

### Core features

| Feature | Description |
|---|---|
| **Group-clustered memory** | Four built-in groups (`project_dna`, `problem_tracking`, `decision_trail`, `code_history`) plus user-defined groups. |
| **Checked-in storage** | Memory lives in `.zhar/mem/` as plain JSON files — diff-able and reviewable in git. |
| **Agent export** | `zhar export` produces a compact text snapshot suitable for injection into agent context. |
| **Source markers** | `%ZHAR:<id>%` tokens link nodes to specific lines in source files. |
| **Facts store** | Independent string KV store used to parameterise agent templates and stack rendering. |
| **Stack system** | GitHub-backed bucket cache, a per-project registry, and a template engine for rendering skills, instructions, agents, and hooks. |
| **GC and verify** | `zhar gc` archives resolved issues and deletes expired nodes. `zhar verify` reports structural inconsistencies. |
| **Pluggable backends** | JSON is the default backend. SQLite, mem0, and zep are planned extension points. |
| **User-defined groups** | Drop a `mem_<name>.py` file in `.zhar/cfg/` to add custom node types following the same contract as built-ins. |

### Why not just use git?

Git is excellent at tracking code changes. It is not designed to store durable semantic context such as:

- why a choice was made
- what is still unresolved
- what an agent must not break
- which project constraints are non-negotiable

zhar complements git. It never stores what git already owns.

### Who it's for

- AI coding agents that need persistent project context across sessions
- Developers who want a lightweight memory layer on top of git
- Teams that want architectural decisions and ongoing issues to stay close to the code

---

## Quick Start

Requires Python `3.12+`.

```bash
uv add zhar          # or: pip install zhar
uv run zhar init
```

That creates:

```text
.zhar/
  mem/
  cfg/
```

Create the project goal (singleton — only one active allowed):

```bash
uv run zhar add project_dna core_goal "Build a durable memory layer for this repo"
```

Add a requirement with metadata:

```bash
uv run zhar add project_dna core_requirement "Never lose architecture decisions" --meta priority=high
```

Add an ADR and attach the body:

```bash
uv run zhar add decision_trail adr "Use checked-in project memory"
uv run zhar note <node-id> "## Context

Chat context is ephemeral.

## Decision

Store durable project memory in .zhar/."
```

Create a supplemental note attached to an existing node:

```bash
uv run zhar add-note <target-id> "Extra context that should stay out of normal exports"
```

Check the store:

```bash
uv run zhar status
uv run zhar query --group decision_trail
uv run zhar show <node-id>
```

Show attached notes for matched nodes:

```bash
uv run zhar query --q "migration" --note-depth 1
```

Import a legacy zmem graph:

```bash
uv run zhar migrate zmem path/to/.zmem
```

---

## Memory Groups

zhar organizes memory into groups. Each group is stored as its own JSON file under `.zhar/mem/`.

### project_dna

Stable, high-level project context. Rarely changes.

| Type | Singleton | Memory-backed | Valid statuses | Key metadata |
|---|---|---|---|---|
| `core_goal` | yes | no | `active`, `archived` | `agent` |
| `core_requirement` | no | yes | `active`, `archived` | `agent`, `priority` (low/med/high) |
| `product_context` | no | yes | `active`, `archived` | `agent`, `audience` |
| `stakeholder` | no | no | `active`, `archived` | `agent`, `role`, `authority_scope` |

### problem_tracking

Live issues and blockers.

| Type | Memory-backed | Valid statuses | Key metadata |
|---|---|---|---|
| `known_issue` | yes | `active`, `resolved`, `archived` | `agent`, `severity` (low/med/high/critical), `issue_type` (bug/debt/design), `commit_hash` |
| `blocked` | no | `active`, `resolved` | `agent`, `blocker_ref` |

### decision_trail

Architectural decisions and research findings.

| Type | Memory-backed | Valid statuses | Key metadata |
|---|---|---|---|
| `adr` | yes | `proposed`, `accepted`, `superseded` | `agent` |
| `decision` | no | `active`, `superseded`, `archived` | `agent`, `commit_hash`, `alternatives_considered`, `tradeoffs` |
| `lesson_learned` | yes | `active`, `archived` | `agent`, `trigger_event` |
| `research_finding` | yes | `active`, `archived` | `agent`, `outcome` (adopted/rejected/deferred), `source_ref` |

### code_history

Code-level change records that complement `git log`.

| Type | Memory-backed | Valid statuses | Key metadata |
|---|---|---|---|
| `file_change` | no | `active`, `stale`, `archived` | `agent`, `commit_hash`, `path`, `significance` (breaking/refactor/patch/feature) |
| `function_change` | no | `active`, `stale`, `archived` | `agent`, `commit_hash`, `function_name`, `affected_callsites` |
| `breaking_change` | yes | `active`, `archived` | `agent`, `commit_hash`, `what_broke`, `migration_note` |
| `revert_note` | no | `active`, `archived` | `agent`, `commit_hash`, `reverted_commit`, `reason` |

### notes

Additive supplemental notes that attach to other nodes. Hidden from normal `export` output. Only visible in `query` when you pass `--note-depth`.

---

## Daily Workflow

1. Add stable constraints to `project_dna`.
2. Record active bugs or debt in `problem_tracking`.
3. Capture important decisions in `decision_trail`.
4. Link code-level changes in `code_history` with source markers.
5. Run verify to catch incomplete records.

Common commands:

```bash
uv run zhar status
uv run zhar query --q "orjson"
uv run zhar export
uv run zhar export --status archived
uv run zhar verify
uv run zhar gc --dry-run
```

### Export boundaries

By default, `zhar export` exports only the statuses each node type considers current:

| Group / type | Exported statuses |
|---|---|
| `project_dna` | `active` |
| `problem_tracking` | `active` |
| `decision_trail/adr` | `accepted` |
| `decision_trail/decision`, `lesson_learned`, `research_finding` | `active` |
| `code_history` | `active` |
| `notes` | excluded |

Pass `--status` to override the default boundary for a specific slice:

```bash
uv run zhar export --status superseded
```

### GC and verify

```bash
uv run zhar gc            # archive resolved known_issues, delete expired nodes
uv run zhar gc --dry-run  # preview without writing
uv run zhar verify        # report MISSING_SINGLETON, MISSING_CONTENT, BROKEN_SOURCE
```

---

## Source Markers

zhar can connect memory nodes to real code locations using `%ZHAR:<id>%` markers.

Embed the marker token anywhere in a source file:

```python
# %ZHAR:abcd%
def important_function() -> None:
    ...
```

After adding markers, sync them into memory:

```bash
uv run zhar scan .
```

That updates each node's `source` field to:

```text
src/zhar/mem/store.py::30::%ZHAR:4f8b%
```

Markers are scanned in `.py`, `.ts`, `.js`, `.md`, `.toml`, `.yaml`, and `.yml` files by default. Hidden directories (`.git`, `.zhar`) are skipped.

Do not manually edit the `source` field — always let `zhar scan` write it.

---

## Facts

Facts are an independent string-only key-value store used to drive stack template rendering.

- Project facts live in `.zhar/facts.json`.
- Global facts live in `~/.zhar/facts.json`.
- Project facts take precedence over global facts when both define the same key.

```bash
uv run zhar facts set primary_language python
uv run zhar facts set test_runner pytest
uv run zhar facts set python_min_version 3.12
uv run zhar facts list
```

Facts values must always be strings. Non-string values are rejected.

---

## Stack: Skills, Instructions, and Agents

The stack system lets you maintain agent instruction files, skills, instructions, and hooks from versioned GitHub source repos. Templates are rendered using project facts and live memory, then written to your project's output directory (`.github/agents/` by default).

### Concepts

| Concept | Description |
|---|---|
| **Bucket** | A GitHub repo cached locally at `~/.zhar/stack/`. Provides source files for rendering. |
| **Registry** | Per-project manifest at `.zhar/cfg/stack.json`. Records which items are installed and from which bucket. |
| **Stack item** | A named entry with a `kind` (`agent`, `instruction`, `skill`, or `hook`) that points to a source file in a bucket. |
| **Template** | A source file written in the `%%ZHAR.*%%` language. Rendered against facts + memory at sync time. |

### Managing buckets

```bash
uv run zhar stack bucket add org/repo              # cache a GitHub repo (main branch)
uv run zhar stack bucket add org/repo --branch dev # cache a specific branch
uv run zhar stack bucket list                      # show cached repos
uv run zhar stack bucket remove org/repo           # delete from cache
```

Buckets require `zuu` for the initial `add` (network pull). Read operations (`list`, `path_for`) work without it.

### Installing and syncing items

```bash
# Register an item from a cached bucket
uv run zhar stack install my-agent org/repo \
  --kind agent \
  --source agents/base.md

uv run zhar stack install python-skill org/repo \
  --kind skill \
  --source skills/python.md

uv run zhar stack list           # show all installed items
uv run zhar stack uninstall my-agent

# Render all items and write output files
uv run zhar stack sync
uv run zhar stack sync --dry-run           # preview without writing
uv run zhar stack sync --out .github/copilot   # custom output directory
```

Output filename is determined by kind:

| Kind | Output file |
|---|---|
| `agent` | `<name>.agent.md` |
| `instruction` | `<name>.instructions.md` |
| `skill` | `<name>.skill.md` |
| `hook` | `<name>.hook.md` |

### Template language

Templates use the `%%ZHAR.*%%` namespace. A token must be the **sole content of its line** to be parsed as a template directive. Comment lines start with `//`.

#### Condition accumulation

```
%%ZHAR.FACT(primary_language == python)%%    AND condition
%%ZHAR.FACT(test_runner == pytest)%%         AND with previous FACT
%%ZHAR.ORFACT(primary_language == typescript)%%  OR a new AND-group
```

`FACT` lines accumulate into AND-groups. `ORFACT` opens a new OR-group. The accumulated result feeds the next `IF` block.

#### Condition expression syntax

| Syntax | Meaning |
|---|---|
| `key == value` | equality |
| `key != value` | inequality |
| `key < value`, `key >= value` etc. | ordered comparison (string) |
| `key_ver >= 3.12` | version comparison (requires `packaging`) |
| `key in [a, b, c]` | membership in list |
| `key in some_string` | substring check |
| `and`, `or`, `not` | connectors (case-insensitive) |

#### Branching

```
%%ZHAR.IF%%
%%ZHAR.IFTRUE%%
  content when condition is true
%%ZHAR.IFFALSE%%
  content when condition is false
%%ZHAR.IFEND%%
```

`IFFALSE` is optional. IFs can be nested — each `IFEND` closes the innermost open block.

#### Memory conditions

```
%%ZHAR.MEMCOND(len(decision_trail) > 0)%%
%%ZHAR.IF%%
%%ZHAR.IFTRUE%%
  %%ZHAR.MEM(decision_trail)%%
%%ZHAR.IFEND%%
```

`MEMCOND` evaluates a Python expression against the memory groups dict. `MEM` emits the result of a Python expression evaluated against the same dict.

#### Inline content

```
%%ZHAR.RTEXT_START%%
This text is emitted verbatim regardless of conditions.
%%ZHAR.RTEXT_END%%
```

#### Chunk and skill references

```
%%ZHAR.RCHUNK(shared/header.md)%%      always inlined verbatim, no re-parse
%%ZHAR.RSKILL(python)%%                skill reference
%%ZHAR.RSKILL(org/repo:python)%%       skill from a specific bucket repo
```

`RCHUNK` is always expanded inline. `RSKILL` behaviour depends on the item kind:

- When `kind=skill`: skills are eagerly inlined during `stack sync` so distributed skill files are self-contained.
- For all other kinds (`agent`, `instruction`, `hook`): `RSKILL` is left verbatim so the consuming tool (e.g. `zhar agent get`) can resolve skills at runtime against the live workspace.

#### Generating a single agent file on demand

```bash
uv run zhar agent get my-agent
```

This renders the registered agent source against live facts without writing a file. `RSKILL` tokens are resolved at this point.

---

## Source Bucket Shape

A source bucket is any GitHub repository. zhar imposes no required directory structure, but the following layout is recommended for a repo that provides multiple kinds:

```text
my-agents-repo/
  agents/
    base.md           # %%ZHAR.*%% template — kind=agent
    python-agent.md
  instructions/
    code-review.md    # kind=instruction
  skills/
    python.md         # kind=skill — RSKILL tokens eagerly inlined on sync
    testing.md
  hooks/
    pre-commit.md     # kind=hook
  shared/
    header.md         # shared chunk, referenced via RCHUNK
    footer.md
```

A minimal skill file:

```markdown
// python skill — %%ZHAR.*%% template
%%ZHAR.FACT(primary_language == python)%%
%%ZHAR.IF%%
%%ZHAR.IFTRUE%%
# Python conventions

%%ZHAR.RCHUNK(shared/python-style.md)%%
%%ZHAR.IFFALSE%%
// not a Python project — emit nothing
%%ZHAR.IFEND%%
```

A minimal agent file that conditionally includes a skill and a memory snapshot:

```markdown
// base agent — %%ZHAR.*%% template
# Project agent context

%%ZHAR.RSKILL(python)%%

%%ZHAR.MEMCOND(len(project_dna) > 0)%%
%%ZHAR.IF%%
%%ZHAR.IFTRUE%%
## Memory

%%ZHAR.MEM(project_dna)%%
%%ZHAR.IFEND%%
```

Rules for buckets:

- Commit template files at stable paths — the registry stores the exact `source_path` at install time.
- Put shared chunks in a dedicated directory (e.g. `shared/`) so `RCHUNK` paths are unambiguous.
- Skills should be self-contained after `sync` (all `RCHUNK` resolved, all `RSKILL` inlined).
- Agents and instructions may leave `RSKILL` verbatim — they are resolved by `zhar agent get` at runtime.

---

## Extending zhar

### User-defined memory groups

Drop a `mem_<name>.py` file into `.zhar/cfg/`. The file must export a module-level `GROUP: GroupDef` variable. It is loaded automatically by `MemStore` at startup alongside the four built-ins.

```python
# .zhar/cfg/mem_ops.py
from dataclasses import dataclass
from typing import Literal
from zhar.mem.group import GroupDef, NodeTypeDef

@dataclass
class RunbookMeta:
    agent: str = ""
    severity: Literal["low", "med", "high"] = "med"

GROUP = GroupDef(
    name="ops",
    node_types=[
        NodeTypeDef(
            name="runbook",
            meta_cls=RunbookMeta,
            valid_statuses=["active", "archived"],
            default_status="active",
            memory_backed=True,
        ),
    ],
)
```

Once added, the `ops` group is available in all CLI commands:

```bash
uv run zhar add ops runbook "Deploy procedure for service X" --meta severity=high
uv run zhar query --group ops
```

### Runtime context providers

A `GroupDef` can include `RuntimeContextProvider` instances that gather live external context during `export` and `install`. Each provider receives the current nodes for its group and the project root, then returns a string block appended to the export output.

```python
from zhar.mem.group import (
    GroupDef, NodeTypeDef, RuntimeContextProvider, RuntimeContextRequest
)

def _gather_git_status(req: RuntimeContextRequest) -> str | None:
    import subprocess
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=req.project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.strip()

GROUP = GroupDef(
    name="code_history",
    node_types=[...],
    runtime_context_providers=[
        RuntimeContextProvider(
            name="git_status",
            description="Current working tree status from git",
            gather=_gather_git_status,
        ),
    ],
)
```

Provider failures are converted to explanatory blocks rather than aborting export. Runtime context complements stored memory — it does not replace it.

### Pluggable backends

Each group can be configured to use a different storage backend. The default is `JsonBackend`. Additional backends (`sqlite`, `mem0`, `zep`) are planned extension points registered as optional dependencies:

```toml
# pyproject.toml optional-dependencies
mem0 = ["mem0ai>=0.1"]
zep  = ["zep-python>=2.0"]
```

Custom backends must subclass `BaseBackend` from `zhar.mem.backends.base` and implement the read/write contract defined there.

### Installing zhar as a library

```bash
pip install zhar                  # core only
pip install "zhar[mem0]"          # with mem0 backend
pip install "zhar[zep]"           # with zep backend
```
- Effective facts merge global plus project values, with project values taking precedence.

Use facts for small pieces of configuration that agents or templates should branch on.

Examples:

```bash
uv run zhar facts set primary_language python
uv run zhar facts set test_runner pytest
uv run zhar facts set --scope global package_manager uv
uv run zhar facts list
uv run zhar facts list --scope global
```

## Agent Context File

zhar can generate an agent-facing context file from memory plus facts:

```bash
uv run zhar install
```

That writes:

```text
.github/agents/zhar.agent.md
```

Use it when you want an AI agent to start with project-specific context instead of rebuilding that context from scratch each session.

Remove it with:

```bash
uv run zhar uninstall
```

## Stack Templates

zhar also supports reusable stack items for agents, instructions, skills, and hooks.

Typical flow:

```bash
uv run zhar stack bucket add org/repo
uv run zhar stack install my-agent org/repo --kind agent --source agents/base.md
uv run zhar stack sync
```

This is useful if you want to manage a shared library of agent templates across repos.

## Validation and Maintenance

Use these commands to keep memory healthy:

```bash
uv run zhar verify
uv run zhar gc
uv run zhar gc --dry-run
```

`verify` checks for issues like:

- missing singleton records
- missing markdown content for memory-backed node types
- broken source links

`gc` handles expired nodes and archives resolved known issues.

## Migration

`migrate` is a command group for importing external memory formats into zhar.

Currently supported:

- `zhar migrate zmem <path>`: import a zmem instance using only its `graph.json`

The zmem importer intentionally does not parse `.zmem/memory/*.md` bodies during migration. It maps compatible zmem node types into zhar groups, preserves legacy IDs when possible, and stores the original zmem JSON record as attached note context.

## Repository Layout

The important files are:

```text
.zhar/
  mem/          # one JSON file per group
  cfg/          # user-defined group config and stack registry
  facts.json    # string key-value facts
src/zhar/       # implementation
tests/          # automated test suite
test_src/mem/   # checked-in integration fixture copied from live .zhar/mem
```

## Development

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
```

Run the CLI during development:

```bash
uv run zhar --help
```

## Design Principles

zhar is built around a few strong assumptions:

- memory should be committed to the repo
- stored context should be small, semantic, and reviewable
- source markers should be the canonical link from memory to code
- facts should stay simple and string-only
- git remains the source of truth for raw patch history

## Current State

This project is actively evolving, but the core workflow is already in place:

- grouped memory storage
- validation and garbage collection
- source scanning
- fact-driven agent export
- stack template syncing

If you want to understand the system quickly, start with:

```bash
uv run zhar status
uv run zhar query
uv run zhar export
```
