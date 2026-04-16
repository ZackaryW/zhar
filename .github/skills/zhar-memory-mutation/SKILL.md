---
name: zhar-memory-mutation
description: 'Use when safely mutating zhar durable memory, facts, or source markers through the CLI. Keywords: zhar add, zhar note, facts set, scan, verify, memory routing, safe mutation.'
argument-hint: 'Describe the intended durable change, the likely owning group or node type, and whether markers, facts, or validation commands are involved.'
user-invocable: true
---

# zhar Memory Mutation

## When to Use

- You need to add or update durable zhar memory.
- You need to choose the right owning group before writing memory.
- You are changing facts or source markers and need the safe CLI workflow.
- You want a repeatable mutation checklist instead of only the reference rules.

## Procedure

1. Read current state first with `zhar export`, `zhar status`, `zhar query`, or `zhar show <id>`.
2. Choose the owning group with the priority workflow graph from `instruction-zhar-memory` before writing anything.
3. Use the CLI mutation that matches the change:
   - `zhar add ...` for new primary records.
   - `zhar set-status ...` for lifecycle changes.
   - `zhar note ...` or `zhar add-note ...` for supplemental notes.
   - `zhar facts set` or `zhar facts unset` for facts.
4. Use stdin or environment variables only when the content body is too large for a literal argument and ensure the environment variable already exists.
5. Run `zhar scan` after source-marker edits.
6. Run `zhar show <id>`, `zhar query --note-depth 1`, or `zhar export` to confirm the resulting durable state.
7. Run `zhar verify` after structural changes and `zhar gc` at commit or handoff chokepoints.

## Fast Rules

- Do not edit `.zhar/` JSON or facts files by hand.
- Create the owning semantic record before optional `code_history` breadcrumbs.
- Use `notes` only for supplemental detail that should stay out of normal exports.
- Facts are string-to-string only.
- Archive or supersede durable records when appropriate; do not silently discard project history.

## References

- [memory workflow](../../instructions/zhar-memory.instructions.md)
- [stack/customization layout](../../instructions/zhar-stack.instructions.md)