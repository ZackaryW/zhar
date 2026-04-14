---
name: zhar-template-resolution
description: 'Use when debugging or explaining zhar template rendering, bucket resolution, zhar agent get, zhar stack sync, or %%ZHAR.*%% marker behavior. Keywords: RSKILL, RCHUNK, FACT, MEMCOND, MEM, agent get, stack sync, bucket.'
argument-hint: 'Describe the item kind, the marker that is confusing, and whether the question is about agent get or stack sync.'
user-invocable: true
---

# zhar Template Resolution

## When to Use

- A template output does not match expectations.
- You need to explain whether a marker is eager, lazy, conditional, or verbatim.
- You need to compare `zhar agent get` with `zhar stack sync`.
- You are debugging bucket lookup, `source_path`, or nested skill behavior.

## Procedure

1. Identify the installed item.
   - Read `.zhar/cfg/stack.json` and note `repo`, `branch`, `kind`, and `source_path`.
2. Confirm the source exists in the cached bucket.
   - Resolve the repo from `~/.zhar/stack/` and inspect the referenced file.
3. Identify which markers appear.
   - `FACT` / `ORFACT` build conditions.
   - `MEMCOND` uses current group counts.
   - `IF` / `IFTRUE` / `IFFALSE` / `IFEND` gate output.
   - `RCHUNK` always inlines a file.
   - `RSKILL` is lazy unless syncing an item whose `kind` is `skill`.
   - `MEM` evaluates a Python expression over the memory groups.
4. Verify inputs.
   - Confirm effective facts.
   - Confirm group contents used by `MEMCOND` and `MEM`.
5. Compare execution paths.
   - `agent get` is a runtime render with `expand_skills=False`.
   - `stack sync` uses `expand_skills=(kind == "skill")`.
6. Explain or fix the mismatch.
   - If behavior is correct, document it.
   - If comments or docs disagree with code/tests, update them to match implementation or change the code intentionally.

## Fast Rules

- `RCHUNK` always resolves now.
- `RSKILL` resolves only during `stack sync` when the rendered item kind is `skill`.
- `agent get` currently leaves `RSKILL` verbatim for every kind.
- If a marker line is mixed with surrounding text, it is treated as plain text rather than a token.
- A token must be the sole content of its line to be parsed.

## References

- [agent get behavior](../../instructions/zhar-agent-get.instructions.md)
- [stack/customization layout](../../instructions/zhar-stack.instructions.md)