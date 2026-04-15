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
- Use `zhar add ... --content TEXT` when the markdown body is already available as a literal argument; use `--content -` to read the body from stdin.
- Use `zhar add ... --from-env NAME` or `--content-var NAME` only when `NAME` is an existing environment variable that contains the full body text.
- In PowerShell, set `$env:NAME = @'...'@` before invoking zhar; do not pass a shell-local `$NAME` variable to `--from-env` unless that value is itself the name of an existing environment variable.
- For non-memory-backed node types, `zhar add ... --from-env NAME` and `--content-var NAME` create an attached supplemental `notes/note` record instead of inline node content.
- Use `zhar set-status <id> <status>` to move an existing node through its valid lifecycle states.
- Use `zhar note <id> "..."` for a literal body, `zhar note <id> -` to read from stdin, or `zhar note <id> --from-env NAME` / `--content-var NAME` to read the body from an environment variable.
- Use `zhar add-note <target-id> "..."`, `zhar add-note <target-id> -`, or `zhar add-note <target-id> --from-env NAME` / `--content-var NAME` for supplemental notes that should stay out of normal exports.
- Use `zhar remove <id>` or `zhar prune ...` only when a record is incorrect, duplicate, or intentionally transient; prefer lifecycle status changes when the node should remain in project history.
- Use `zhar facts set [--scope project|global] <key> <value>` for facts, and `zhar facts unset` instead of hand-editing facts files.
- Use `zhar scan` after embedding `%ZHAR:<id>%` in source.
- Use `zhar show <id>`, `zhar query --note-depth 1`, or `zhar export` after a mutation to confirm the resulting state.
- Use `zhar migrate zmem <path>` when importing legacy zmem state; do not manually rewrite migrated JSON into `.zhar/mem/`.

## Core Invariants

- Every node ID is hex, 4+ characters, and unique within the project.
- `id`, `group`, `node_type`, and `created_at` are immutable after creation.
- Group and node-type boundaries are part of the data model; do not blur them by storing issue tracking in `project_dna`, decisions in `code_history`, or supplemental commentary outside `notes`.
- `code_history` is complementary memory. It should capture file/function/breaking breadcrumbs, not replace the owning semantic group for architectural, workflow, or decision-level changes.
- Singleton node types may have at most one active node.
- Facts are always string-to-string across project, global, and effective scopes.
- Metadata is validated against each node type's dataclass fields. `Literal`-backed metadata rejects free-form values, so use the documented value sets below or verify the group definition/tests before inventing a value.
- `orjson` is the only JSON serializer used by zhar.
- `.zhar/` is committed to source control. Only `.zhar/**/__pycache__/` is ignored.
- The `notes` group is supplemental memory. It attaches to primary nodes through `metadata.target_ids` and is excluded from normal exports.

## Built-in Group Reference

### project_dna

| Type | Singleton | Memory-backed | Statuses | Metadata |
|---|---|---|---|---|
| `core_goal` | yes | no | `active`, `archived` | `agent` |
| `core_requirement` | no | yes | `active`, `archived` | `agent`, `priority (low|med|high)` |
| `product_context` | no | yes | `active`, `archived` | `agent`, `audience` |
| `stakeholder` | no | no | `active`, `archived` | `agent`, `role`, `authority_scope` |

### problem_tracking

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `known_issue` | yes | `active`, `resolved`, `archived` | `agent`, `severity (low|med|high|critical)`, `issue_type (bug|debt|design)`, `commit_hash` |
| `blocked` | no | `active`, `resolved` | `agent`, `blocker_ref` |

### decision_trail

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `adr` | yes | `proposed`, `accepted`, `superseded` | `agent` |
| `decision` | no | `active`, `superseded`, `archived` | `agent`, `commit_hash`, `alternatives_considered`, `tradeoffs` |
| `lesson_learned` | yes | `active`, `archived` | `agent`, `trigger_event` |
| `research_finding` | yes | `active`, `archived` | `agent`, `outcome (adopted|rejected|deferred)`, `source_ref` |

### architecture_context

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `architecture` | yes | `active`, `stale`, `archived` | `agent`, `diagram_ref` |
| `design_pattern` | yes | `active`, `archived` | `agent` |
| `component_rel` | no | `active`, `deprecated`, `archived` | `agent`, `from_component`, `to_component`, `rel_type`, `contract` |
| `tech_stack` | no | `active`, `stale`, `archived` | `agent`, `language`, `framework`, `version` |
| `tech_setup` | yes | `active`, `stale`, `archived` | `agent` |
| `tech_constraint` | yes | `active`, `archived` | `agent`, `category (perf|security|compliance|budget)` |
| `env_config` | no | `active`, `stale`, `archived` | `agent`, `env (dev|staging|prod)` |
| `external_dep` | no | `active`, `deprecated`, `archived` | `agent`, `service_name`, `api_version`, `failure_modes` |

### code_history

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `file_change` | no | `active`, `stale`, `archived` | `agent`, `commit_hash`, `path`, `significance (breaking|refactor|patch|feature)` |
| `function_change` | no | `active`, `stale`, `archived` | `agent`, `commit_hash`, `function_name`, `affected_callsites` |
| `breaking_change` | yes | `active`, `archived` | `agent`, `commit_hash`, `what_broke`, `migration_note` |
| `revert_note` | no | `active`, `archived` | `agent`, `commit_hash`, `reverted_commit`, `reason` |

### links

| Type | Memory-backed | Statuses | Metadata |
|---|---|---|---|
| `node_link` | no | `active`, `archived` | `agent`, `from_id`, `to_id`, `rel_type` |

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
- `session_challenge_enabled` controls whether suspicious transient session nodes are reported and whether challenge state is surfaced in session-aware runtime output.
- `session_challenge_agent` names the review agent surfaced by `zhar session need-challenge` and session-aware runtime exports.

## Session Runtime

- Transient session state is separate from durable `.zhar/` memory and is stored under the OS temp cache at `zhar_cache/session/`.
- The active session ID comes from `ZHAR_SESSION_ID`; if it is absent, zhar generates one for the current process.
- Use root-level `--no-session` to disable transient session tracking for one CLI invocation.
- `zhar show <id>` records session inspection state when tracking is enabled.
- `zhar show <id> --relation-depth N` records expanded inspection when `N > 0`, which is distinct from a shallow show event.
- Use `zhar session list` to inspect visible transient sessions, prioritized to the current project and cwd.
- Use `zhar session adopt <session-id>` to set `ZHAR_SESSION_ID` for the current process.
- Use `zhar session current` to inspect the active session; `zhar session current --format json` returns the same runtime state in structured form.
- Use `zhar session clear` to delete the current transient session file.
- Use `zhar session need-challenge` to print suspicious node IDs only when challenge reporting is enabled by facts.

## Query and Export

- `zhar query` defaults to all non-`notes` groups unless you pass explicit group/type filters.
- Use `zhar query --note-depth N` to include attached supplemental notes under matching primary nodes.
- Use `zhar show <id> --relation-depth N` to append related nodes without leaving the seed set's active status and tag boundary.
- `zhar export` omits the `notes` group by default and exports only each node type's current statuses when `--status` is not provided.
- Use `zhar export --tag TAG` when you need a namespace- or project-scoped snapshot; repeated `--tag` options are AND-combined.
- Use `zhar export --relation-depth N` to expand related nodes from the exported seed set.
- `zhar export --relation-depth N` preserves the active tag and status boundary for expanded nodes; it does not cross into differently tagged or non-current nodes.
- Relation-depth expansion uses built-in `links/node_link` edges through `metadata.from_id` and `metadata.to_id`.
- `component_rel` is not the generic linking mechanism; it remains an architecture node type that explains relationships between components.
- Dangling links are ignored on read so deleted or filtered targets do not break traversal.
- Default exports omit the built-in `links` group unless you explicitly request it.
- Use `zhar export --with-runtime-context` when you want group-defined runtime context blocks included in the output.
- Group runtime context is complementary live data gathered at export time. It does not mutate durable memory and does not replace the stored node set.
- When transient session state exists, `zhar export --with-runtime-context` also appends a `Session state` block with `session_id`, shown and suspicious counts, `challenge_enabled`, optional `challenge_agent`, and per-node score lines.
- `zhar export --format json --with-runtime-context` returns the same runtime information under a structured `runtime_context` payload, including any session state.

## Memory Routing Heuristic

- Prefer the owning semantic group first: architecture and traversal semantics belong in `architecture_context`; design choices and routing rationale belong in `decision_trail`; goals and requirements belong in `project_dna`.
- Add `code_history/file_change` only when the file-level breadcrumb is independently useful after the semantic record exists.
- Do not let repeated CLI or implementation work default into `code_history` when the durable takeaway is really a change in memory semantics or architectural behavior.

## Priority Workflow Graph

Default owner-first routing order for standard project policies:

```text
Start
 |
 +-- Goal, requirement, audience, or product constraint?
 |     -> project_dna
 |
 +-- Active bug, blocker, operational failure, or unresolved risk?
 |     -> problem_tracking
 |
 +-- Architecture, runtime model, data contract, traversal rule, group/node semantics,
 |   component relationships, or technical operating context?
 |     -> architecture_context
 |
 +-- Decision, tradeoff, rationale, routing rule, research result, or lesson learned?
 |     -> decision_trail
 |
 +-- File/function/breaking breadcrumb that remains useful after the semantic
 |   record already exists?
 |     -> code_history
 |
 +-- Extra detail attached to a primary record?
	 -> notes
```

Priority rule:

- If multiple branches apply, create the highest-priority semantic record first, then add lower-priority supplemental records only when they remain independently useful.
- `code_history` should usually be last in the routing order, not the first stop.

Customization rule:

- Repositories may customize this graph by editing the repo-local instruction, but the default should remain owner-first and `code_history`-last unless the project has a stronger policy.
- When customizing, prefer adding or reordering semantic branches instead of weakening the requirement to create an owning semantic record.

Examples:

| Change shape | Primary group | Optional supplemental group |
|---|---|---|
| Goal or non-negotiable requirement update | `project_dna` | `code_history` |
| Runtime traversal or relationship semantics change | `architecture_context` | `code_history` |
| Workflow routing rule or durable rationale | `decision_trail` | `code_history` |
| Memory CLI mutation workflow change | `architecture_context` | `code_history` |
| Active breakage or unresolved regression | `problem_tracking` | `code_history` |
| File breadcrumb after semantic owner already exists | `code_history` | `notes` |

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