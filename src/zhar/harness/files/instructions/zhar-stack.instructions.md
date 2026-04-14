---
description: "Use when editing zhar stack buckets, .github/agents, .github/instructions, .github/skills, or .zhar/cfg/stack.json. Covers how to split content across agents, instructions, skills, hooks, and bucket templates."

---

# zhar Stack and Customization Layout

## Choose the Right Primitive

- Use an `agent` when you need a focused specialist persona with its own tools and boundaries.
- Use an `instruction` when guidance should be discoverable on demand or auto-attached by file pattern.
- Use a `skill` when the task is a repeatable workflow that benefits from step-by-step guidance and bundled references or scripts.
- Use a `hook` when behavior must be deterministic and enforced by shell commands.

## Preferred Split

- Keep agent files small and role-focused.
- Move durable policy, invariants, and reporting requirements into `.github/instructions/*.instructions.md`.
- Move repeatable troubleshooting or operational workflows into `.github/skills/<name>/SKILL.md`.
- Use links between these files rather than duplicating the same reference tables in every place.

## Source Bucket Shape

Recommended layout for a bucket repo that ships multiple item kinds:

```text
bucket-repo/
  agents/
    base.md
  instructions/
    review.md
  skills/
    python.md
    testing.md
  hooks/
    pre-commit.md
  shared/
    header.md
    footer.md
```

Guidelines:

- Keep source files at stable paths; registry entries persist `source_path` exactly.
- Put reusable fragments in a dedicated shared directory and include them through `%%ZHAR.RCHUNK(...)%%`.
- Keep nested skill references explicit with `%%ZHAR.RSKILL(...)%%` unless you specifically want a skill file to inline them during `stack sync`.
- Prefer one concern per file instead of a single monolithic agent definition.

## Registry and Output Rules

- Cached bucket repos live under `~/.zhar/stack/`.
- The per-project registry lives at `.zhar/cfg/stack.json`.
- `zhar stack install <name> <repo> --kind <kind>` records the item in the registry using the same cached-source lookup model as `stack fetch`.
- `--source <path>` is optional and acts as an explicit override that is still validated against cached sources.
- `zhar stack sync` renders all installed items and writes them to `.github/agents/` by default.

## Lookup Strategy

- `zhar stack fetch` resolves directly from cached bucket sources. It does not consult the workspace install registry.
- `zhar stack install` uses the same cached-source lookup model to resolve the source path before recording it in `.zhar/cfg/stack.json`.
- Source discovery currently searches cached repos for these shapes:
  - `.github/agents/*.agent.md`
  - `.github/instructions/*.instructions.md`
  - `.github/skills/<name>/SKILL.md`
  - `.github/hooks/*.hook.md`
  - legacy root-level `agents/*`, `instructions/*`, `skills/*`, `skills/<name>/SKILL.md`, and `hooks/*`
- Accepted lookup keys are:
  - bare discovered name such as `cline-memory-bank`
  - repo-qualified name such as `org/repo:cline-memory-bank`
  - exact cached `source_path` such as `.github/skills/cline-memory-bank/SKILL.md`
- When multiple cached repos expose the same bare name, the bare lookup is ambiguous. Use the repo-qualified name or exact source path instead.
- `stack fetch --fuzzy-conf` may choose the top-scoring cached source when there is no exact match. Auto-resolving `stack install` is exact-match only today.
- If the repo, branch, or kind is already known, the resolver narrows candidates before matching. This is why `stack install <name> <repo> --kind <kind>` can resolve a path automatically.

Output suffixes:

- `agent` -> `<name>.agent.md`
- `instruction` -> `<name>.instructions.md`
- `skill` -> `<name>.skill.md`
- `hook` -> `<name>.hook.md`

## Common Commands

```bash
zhar stack bucket add org/repo --branch main
zhar stack bucket list
zhar stack bucket remove org/repo

zhar stack install my-agent org/repo --kind agent
zhar stack install python-skill org/repo --kind skill

zhar stack list
zhar stack sync
zhar stack sync --dry-run
```

## Working Rule

- When a stack behavior question depends on template markers or `agent get`, follow [zhar-agent-get.instructions.md](./zhar-agent-get.instructions.md) and [zhar-template-resolution](../skills/zhar-template-resolution/SKILL.md).
- When a stack behavior question is about how files are found, installed, or fetched, treat this instruction as authoritative for cached-source lookup before falling back to the agent file.