---
name: zhar-harness-workflow
description: 'Use when editing repo-authored harness files under .github, syncing them into src/zhar/harness/files, or verifying the runtime mirrored copy with harness commands. Keywords: harness get, export-mem-context, sync_harness_files.py, mirrored files, .github, runtime view.'
argument-hint: 'Describe which harness files changed, whether the mirror needs syncing, and whether you need runtime verification or memory-context export.'
user-invocable: true
---

# zhar Harness Workflow

## When to Use

- You are editing `.github/agents/`, `.github/instructions/`, or `.github/skills/` in this repo.
- You need to confirm what `zhar harness get` will expose at runtime.
- You need to regenerate the live memory-context export.
- You want to check whether the mirrored harness files are stale before commit or push.

## Procedure

1. Edit the source-of-truth files under `.github/`.
2. Discover the runtime keys with `zhar harness get --help` when you need to inspect available mirrored content.
3. Use `zhar harness install <flattened-key>` when you need to write a mirrored runtime file back into a workspace `.github/` destination.
4. Sync the mirror with `uv run python scripts/sync_harness_files.py`.
5. Verify the runtime view with `zhar harness get <flattened-key>` against the mirrored copy in `src/zhar/harness/files/`.
6. If the task involves the generated memory-context snapshot, run `uv run zhar harness export-mem-context` or pass `--out` for an explicit destination.
7. Before push, run `uv run python scripts/sync_harness_files.py --check` so stale or unexpected mirrored files fail fast.

## Fast Rules

- Treat `.github/` as the source of truth during development.
- Treat `src/zhar/harness/files/` as the runtime mirror read by `zhar harness get`.
- Treat `zhar harness install <flattened-key>` as the way to materialize one mirrored authored file into `.github/`.
- If `.github/` and `harness get` disagree, the mirror is stale until the sync script runs.
- Use `zhar harness get --help` as the discoverability entry point, not guesswork about keys.
- Keep `export-mem-context` separate from static authored agent files.

## References

- [README harness workflow](../../README.md)
- [stack/customization layout](../../instructions/zhar-stack.instructions.md)
- [agent-get behavior](../../instructions/zhar-agent-get.instructions.md)