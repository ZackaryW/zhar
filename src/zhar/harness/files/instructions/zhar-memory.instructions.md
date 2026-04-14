---
description: "Use when working with zhar-backed memory, node CRUD, facts, source markers, or scan/gc/verify workflows. Covers safe mutation, invariants, validation, and reporting."
---

# zhar Memory Workflow

## Preflight

- Read memory before writing. Use `zhar export`, `zhar status`, `zhar query`, or `zhar show <id>`.
- If the task mentions errors, warnings, or failures, inspect Problems before choosing a fix.
- Choose the correct group and node type before adding or updating records.

## Safe Mutation Rules

- Use `zhar add <group> <node_type> ...` for new nodes.
- Use `zhar note <id> --content ...` for markdown content on memory-backed nodes.
- Use `zhar facts set <key> <value>` for facts.
- Use `zhar scan` after embedding `%ZHAR:<id>%` in source.
- Use `zhar show <id>` or `zhar export` after a mutation to confirm the resulting state.

## Core Invariants

- Every node ID is hex, 4+ characters, and unique within the project.
- `id`, `group`, `node_type`, and `created_at` are immutable after creation.
- Singleton node types may have at most one active node.
- Facts are always string-to-string.
- `orjson` is the only JSON serializer used by zhar.
- `.zhar/` is committed to source control. Only `.zhar/**/__pycache__/` is ignored.

## Built-in Group Reference

### project_dna

| Type | Singleton | Memory-backed | Statuses | Metadata |
|---|---|---|---|---|
| `core_goal` | yes | no | `active`, `archived` | `agent` |
| `core_requirement` | no | yes | `active`, `archived` | `agent`, `priority` |
| `product_context` | no | yes | `active`, `archived` | `agent`, `audience` |
| `stakeholder` | no | no | `active`, `archived` | `agent`, `role`, `authority_scope` |

### problem_tracking

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `known_issue` | yes | `active`, `resolved`, `archived` | `agent`, `severity`, `issue_type`, `commit_hash` |
| `blocked` | no | `active`, `resolved` | `agent`, `blocker_ref` |

### decision_trail

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `adr` | yes | `proposed`, `accepted`, `superseded` | `agent` |
| `decision` | no | `active`, `superseded`, `archived` | `agent`, `commit_hash`, `alternatives_considered`, `tradeoffs` |
| `lesson_learned` | yes | `active`, `archived` | `agent`, `trigger_event` |
| `research_finding` | yes | `active`, `archived` | `agent`, `outcome`, `source_ref` |

### code_history

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `file_change` | no | `active`, `stale`, `archived` | `agent`, `commit_hash`, `path`, `significance` |
| `function_change` | no | `active`, `stale`, `archived` | `agent`, `commit_hash`, `function_name`, `affected_callsites` |
| `breaking_change` | yes | `active`, `archived` | `agent`, `commit_hash`, `what_broke`, `migration_note` |
| `revert_note` | no | `active`, `archived` | `agent`, `commit_hash`, `reverted_commit`, `reason` |

## Memory-backed Types

These node types must carry markdown content:

- `project_dna/core_requirement`
- `project_dna/product_context`
- `problem_tracking/known_issue`
- `decision_trail/adr`
- `decision_trail/lesson_learned`
- `decision_trail/research_finding`
- `code_history/breaking_change`

## Source Markers

- Marker format is `%ZHAR:<hex-id>%`.
- `zhar scan` writes the `source` field as `path::line::%ZHAR:<id>%`.
- Never hand-edit the `source` field.
- Do not add markers to generated, minified, or vendor files.

## Validation

- Run `zhar verify` after major structural changes or when the user asks for validation.
- Run `zhar gc` at commit chokepoints; it archives resolved `known_issue` nodes and deletes expired nodes.
- Consult Problems after editing touched files and resolve any new issues introduced by your change.

## Reporting

- Report which groups and node IDs changed.
- Report whether facts changed.
- Report whether `scan`, `verify`, and `gc` were run and whether they passed.
- If validation was skipped, say why.