---
description: "Use when working with zhar-backed memory, node CRUD, facts, source markers, or scan/gc/verify workflows. Covers safe mutation, invariants, validation, and reporting."
---

# zhar Memory Workflow

## Preflight

- Read memory before writing. Use `zhar export`, `zhar status`, `zhar query`, or `zhar show <id>`.
- If the task mentions errors, warnings, or failures, inspect Problems before choosing a fix.
- Choose the correct group and node type before adding or updating records.
- Treat understanding group and node delimitations as mandatory before mutation: decide whether the change belongs in `project_dna`, `problem_tracking`, `decision_trail`, `architecture_context`, `code_history`, or `notes` before writing anything.
- Distinguish workspace memory from stack/harness state. Memory lives under `.zhar/`; stack buckets and generated agent files are a separate workflow.

## Safe Mutation Rules

- Use `zhar add <group> <node_type> ...` for new nodes.
- Use `zhar set-status <id> <status>` to move an existing node through its valid lifecycle states.
- Use `zhar note <id> "..."` for a literal body, `zhar note <id> -` to read from stdin, or `zhar note <id> --from-env NAME` to read the body from an environment variable.
- Use `zhar add-note <target-id> "..."` for supplemental notes that should stay out of normal exports.
- Use `zhar remove <id>` or `zhar prune ...` only when a record is incorrect, duplicate, or intentionally transient; prefer lifecycle status changes when the node should remain in project history.
- Use `zhar facts set [--scope project|global] <key> <value>` for facts, and `zhar facts unset` instead of hand-editing facts files.
- Use `zhar scan` after embedding `%ZHAR:<id>%` in source.
- Use `zhar show <id>`, `zhar query --note-depth 1`, or `zhar export` after a mutation to confirm the resulting state.
- Use `zhar migrate zmem <path>` when importing legacy zmem state; do not manually rewrite migrated JSON into `.zhar/mem/`.

## Core Invariants

- Every node ID is hex, 4+ characters, and unique within the project.
- `id`, `group`, `node_type`, and `created_at` are immutable after creation.
- Group and node-type boundaries are part of the data model; do not blur them by storing issue tracking in `project_dna`, decisions in `code_history`, or supplemental commentary outside `notes`.
- Singleton node types may have at most one active node.
- Facts are always string-to-string across project, global, and effective scopes.
- `orjson` is the only JSON serializer used by zhar.
- `.zhar/` is committed to source control. Only `.zhar/**/__pycache__/` is ignored.
- The `notes` group is supplemental memory. It attaches to primary nodes through `metadata.target_ids` and is excluded from normal exports.

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

### architecture_context

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `architecture` | yes | `active`, `stale`, `archived` | `agent`, `diagram_ref` |
| `design_pattern` | yes | `active`, `archived` | `agent` |
| `component_rel` | no | `active`, `deprecated`, `archived` | `agent`, `from_component`, `to_component`, `rel_type`, `contract` |
| `tech_stack` | no | `active`, `stale`, `archived` | `agent`, `language`, `framework`, `version` |
| `tech_setup` | yes | `active`, `stale`, `archived` | `agent` |
| `tech_constraint` | yes | `active`, `archived` | `agent`, `category` |
| `env_config` | no | `active`, `stale`, `archived` | `agent`, `env` |
| `external_dep` | no | `active`, `deprecated`, `archived` | `agent`, `service_name`, `api_version`, `failure_modes` |

### code_history

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `file_change` | no | `active`, `stale`, `archived` | `agent`, `commit_hash`, `path`, `significance` |
| `function_change` | no | `active`, `stale`, `archived` | `agent`, `commit_hash`, `function_name`, `affected_callsites` |
| `breaking_change` | yes | `active`, `archived` | `agent`, `commit_hash`, `what_broke`, `migration_note` |
| `revert_note` | no | `active`, `archived` | `agent`, `commit_hash`, `reverted_commit`, `reason` |

### notes

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `note` | yes | `active`, `archived` | `agent`, `target_ids` |

## Memory-backed Types

These node types must carry markdown content:

- `project_dna/core_requirement`
- `project_dna/product_context`
- `problem_tracking/known_issue`
- `decision_trail/adr`
- `decision_trail/lesson_learned`
- `decision_trail/research_finding`
- `architecture_context/architecture`
- `architecture_context/design_pattern`
- `architecture_context/tech_setup`
- `architecture_context/tech_constraint`
- `code_history/breaking_change`
- `notes/note`

## Facts

- `zhar facts list --scope effective` shows the merged view seen by render/export flows.
- `zhar facts list --scope project` reads `.zhar/facts.json` for the current workspace.
- `zhar facts list --scope global` reads the global user facts store.
- Project facts override global facts in the effective view.

## Query and Export

- `zhar query` defaults to all non-`notes` groups unless you pass explicit group/type filters.
- Use `zhar query --note-depth N` to include attached supplemental notes under matching primary nodes.
- `zhar export` omits the `notes` group by default and exports only each node type's current statuses when `--status` is not provided.
- Use `zhar export --tag TAG` when you need a namespace- or project-scoped snapshot; repeated `--tag` options are AND-combined.
- Use `zhar export --relation-depth N` to expand adjacent `architecture_context/component_rel` nodes from the exported seed set.
- `zhar export --relation-depth N` preserves the active tag and status boundary for expanded nodes; it does not cross into differently tagged relation nodes.
- Relation-depth expansion is currently limited to `architecture_context/component_rel` adjacency through shared `from_component` / `to_component` endpoints.
- Use `zhar export --with-runtime-context` when you want group-defined runtime context blocks included in the output.

## Source Markers

- Marker format is `%ZHAR:<hex-id>%`.
- `zhar scan` writes the `source` field as `path::line::%ZHAR:<id>%`.
- Never hand-edit the `source` field.
- Do not add markers to generated, minified, or vendor files.

## Validation

- Run `zhar verify` after major structural changes or when the user asks for validation.
- `zhar verify` currently reports `MISSING_SINGLETON` and `BROKEN_SOURCE` as warnings, and `MISSING_CONTENT` as info.
- Run `zhar gc` at commit chokepoints; it archives resolved `known_issue` nodes and deletes expired nodes.
- Use `zhar gc --dry-run` and `zhar scan --dry-run` when you need impact visibility before mutating project state.
- Consult Problems after editing touched files and resolve any new issues introduced by your change.

## Reporting

- Report which groups and node IDs changed.
- Report whether facts changed.
- Report whether `scan`, `verify`, and `gc` were run and whether they passed.
- If validation was skipped, say why.