---
description: "Use when documenting or debugging zhar agent get, %%ZHAR.RSKILL%%, %%ZHAR.RCHUNK%%, %%ZHAR.FACT%%, %%ZHAR.MEMCOND%%, %%ZHAR.MEM%%, or template marker resolution. Covers actual runtime behavior and how it differs from stack sync."
---

# zhar agent get and Marker Resolution

## Execution Model

`zhar agent get <name>` does not write files. It renders one installed item from its bucket source and prints the result to stdout.

At runtime it:

1. Loads the named entry from `.zhar/cfg/stack.json`.
2. Resolves the cached repo root through `BucketManager.path_for(repo, branch)`.
3. Loads effective facts from global plus project facts.
4. Opens the memory store and queries every group into the render context.
5. Renders the source file with `ParseContext(..., expand_skills=False)`.
6. Prints the rendered result.

`agent get` is therefore a read-only compilation path over the live workspace state.

## Marker Resolution Rules in agent get

| Marker | agent get behavior |
|---|---|
| `%%ZHAR.FACT(expr)%%` | Adds a fact expression to the current AND-group. |
| `%%ZHAR.ORFACT(expr)%%` | Closes the current AND-group and starts a new OR branch. |
| `%%ZHAR.MEMCOND(expr)%%` | Evaluates a condition against synthetic `<group>_count` facts derived from current memory groups. |
| `%%ZHAR.IF%%` | Opens a conditional block using the accumulated condition state. |
| `%%ZHAR.IFTRUE%%` | Activates the true branch of the innermost IF. |
| `%%ZHAR.IFFALSE%%` | Activates the false branch of the innermost IF. |
| `%%ZHAR.IFEND%%` | Closes the innermost IF block. |
| `%%ZHAR.RTEXT_START%%` / `%%ZHAR.RTEXT_END%%` | Emits the enclosed raw text block if the condition and branch are active. |
| `%%ZHAR.RCHUNK(path)%%` | Always resolves the referenced file through the chunk resolver and inlines its contents verbatim. |
| `%%ZHAR.RSKILL(name)%%` | Preserved verbatim by `agent get` for every item kind because render context uses `expand_skills=False`. |
| `%%ZHAR.MEM(expr)%%` | Evaluates a Python expression against the current memory-group dict and emits the result string. |

## RSKILL vs RCHUNK

- `RCHUNK` is always eagerly resolved and inlined.
- `RSKILL` is not resolved by `agent get` in the current implementation.
- `RSKILL` remains visible in output so the consumer can see explicit skill dependencies.

## agent get vs stack sync

`zhar stack sync` and `zhar agent get` do not treat `RSKILL` the same way.

| Path | `RSKILL` behavior |
|---|---|
| `zhar agent get <name>` | left verbatim for all kinds |
| `zhar stack sync` for `kind=agent` | left verbatim |
| `zhar stack sync` for `kind=instruction` | left verbatim |
| `zhar stack sync` for `kind=hook` | left verbatim |
| `zhar stack sync` for `kind=skill` | eagerly resolved and inlined |

This means nested skills are only expanded during sync when the item being rendered is itself a skill.

## Authority Rule

If comments or older docs claim that `agent get` resolves `RSKILL` inline, do not repeat that behavior as fact. Follow implementation and tests first, then update the docs or code to bring them back into alignment.

## Debug Checklist

1. Confirm the item exists in `.zhar/cfg/stack.json`.
2. Confirm the bucket is cached and the `source_path` exists.
3. Confirm the effective facts that should drive `FACT` and `ORFACT` conditions.
4. Confirm memory groups exist for `MEMCOND` and `MEM` expressions.
5. Use `agent get` when you want the runtime render.
6. Use `stack sync --dry-run` when you want output-generation behavior.
7. If the only difference is nested skills, check whether the item kind is `skill`.