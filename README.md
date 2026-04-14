# zhar

zhar is a project memory tool for codebases that need durable, structured context.

It gives you a checked-in `.zhar/` directory where you can store:

- stable project goals and requirements
- active issues and blockers
- architecture decisions and research findings
- code-history notes linked to real source files
- supplemental notes attached to primary nodes when extra detail should stay out of normal exports

The goal is simple: keep the context that gets lost between sessions, handoffs, and model resets.

## Who It's For

zhar is useful when your repo is worked on by:

- AI coding agents that need persistent project context
- developers who want a lightweight memory layer on top of git
- teams that want architectural decisions and ongoing issues to stay close to the code

If you have ever repeated the same project constraints to a tool or teammate, zhar is meant to reduce that repetition.

## What zhar Stores

zhar organizes memory into four built-in groups:

- `project_dna`: goals, requirements, product context, stakeholders
- `problem_tracking`: known issues and blockers
- `decision_trail`: ADRs, decisions, lessons learned, research findings
- `code_history`: file changes, function changes, breaking changes, revert notes

It also includes a default `notes` group for additive note records that attach to other nodes. Notes are hidden from normal `export` output and only appear in `query` when you opt into linked note expansion.

Each group is stored as its own JSON file under `.zhar/mem/`.

That means the memory is:

- explicit
- reviewable in git
- queryable from the CLI
- available for export into agent context files

## Why Not Just Use Git?

Git is excellent at tracking code changes.
It is not great at storing durable semantic context like:

- why a choice was made
- what is still unresolved
- what an agent must not break
- which project constraints are non-negotiable

zhar is designed to complement git, not replace it.

## Quick Start

Requires Python `3.12+`.

If you are working in this repo:

```bash
uv sync
uv run zhar init
```

That creates:

```text
.zhar/
  mem/
  cfg/
```

Then start adding memory.

Create the project goal:

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

Attach the same note to more than one node:

```bash
uv run zhar add-note <target-id> "Shared migration context" --target <other-target-id>
```

Check what is in the store:

```bash
uv run zhar status
uv run zhar query --group decision_trail
uv run zhar show <node-id>
```

Show attached notes for matched nodes:

```bash
uv run zhar query --q "migration" --note-depth 1
```

Import a legacy zmem graph into zhar using the `migrate` command group and only the `graph.json` surface:

```bash
uv run zhar migrate zmem path/to/.zmem
```

## Daily Workflow

Typical usage looks like this:

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

By default, `zhar export` does not dump every node in the store. It exports only the statuses each node type considers current.

Current export boundaries for the built-in types:

- `project_dna`: `active`
- `problem_tracking`: `active`
- `decision_trail/adr`: `accepted`
- `decision_trail/decision`, `lesson_learned`, `research_finding`: `active`
- `code_history`: `active`
- `notes`: excluded from normal export

If you need a non-default slice, pass `--status` explicitly. An explicit status filter overrides the default current boundary.

## Source Markers

zhar can connect memory nodes to real code locations using `%ZHAR:<id>%` markers.

Example:

```python
# %ZHAR:abcd%
def important_function() -> None:
    ...
```

After adding markers, sync them into memory:

```bash
uv run zhar scan .
```

That updates node `source` fields into a form like:

```text
src/zhar/mem/store.py::30::%ZHAR:4f8b%
```

This is especially useful for `code_history` nodes and agent exports.

## Facts

Facts are a separate string-only key-value store.

- Project facts live in `.zhar/facts.json`.
- Global facts live in `~/.zhar/facts.json`.
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
