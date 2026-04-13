"""sync_stack — render and write installed stack items to output directory.

Iterates over all entries in a ``StackRegistry``, reads the source file from
the ``BucketManager`` cache, renders it through the template engine with the
provided ``TemplateContext``, and writes the result to *output_dir*.

Output filename pattern by kind
--------------------------------
  agent       → <output_dir>/<name>.agent.md
  instruction → <output_dir>/<name>.instructions.md
  skill       → <output_dir>/<name>.skill.md
  hook        → <output_dir>/<name>.hook.md
"""
# %ZHAR:238d% %ZHAR:2a6b%
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from zhar.harness.stack.template import TemplateContext, TemplateError, render_template

if TYPE_CHECKING:
    from zhar.harness.stack.bucket import BucketManager
    from zhar.harness.stack.registry import StackRegistry


# ── output filename mapping ───────────────────────────────────────────────────

_KIND_SUFFIX: dict[str, str] = {
    "agent":       ".agent.md",
    "instruction": ".instructions.md",
    "skill":       ".skill.md",
    "hook":        ".hook.md",
}


# ── result type ───────────────────────────────────────────────────────────────

@dataclass
class SyncResult:
    """Summary of a ``sync_stack`` run."""

    synced:  list[str] = field(default_factory=list)
    """Names of items that were successfully rendered (and written unless dry_run)."""

    skipped: list[str] = field(default_factory=list)
    """Names of items that were intentionally skipped."""

    errors:  list[str] = field(default_factory=list)
    """Descriptive error strings for items that failed."""

    @property
    def total(self) -> int:
        """Total number of items processed."""
        return len(self.synced) + len(self.skipped) + len(self.errors)


# ── sync ──────────────────────────────────────────────────────────────────────

def sync_stack(
    registry: "StackRegistry",
    bucket_mgr: "BucketManager",
    context: TemplateContext,
    output_dir: Path,
    *,
    dry_run: bool = False,
) -> SyncResult:
    """Render all installed stack items and write them to *output_dir*.

    For each item in *registry*:
    1. Resolve the bucket cache path via *bucket_mgr*.
    2. Build a chunk resolver scoped to that repo root.
    3. Render the source file through ``render_template``.
    4. Write the output file (skipped when ``dry_run=True``).

    Errors are caught per-item so that one failure does not abort the rest.

    Parameters
    ----------
    registry:
        The ``StackRegistry`` holding installed item metadata.
    bucket_mgr:
        A ``BucketManager`` (or compatible duck-type) for resolving repo paths.
    context:
        Base ``TemplateContext`` with facts and memory groups.  The
        ``chunk_resolver`` is replaced per-item with one scoped to the item's
        repo root.
    output_dir:
        Directory where rendered files are written.
    dry_run:
        If ``True``, render but do not write to disk.

    Returns
    -------
    SyncResult
    """
    result = SyncResult()
    output_dir.mkdir(parents=True, exist_ok=True)

    for item in registry.list_items():
        name = item["name"]
        kind = item["kind"]
        repo = item["repo"]
        branch = item["branch"]
        source_path = item["source_path"]

        try:
            # Resolve the cached repo root
            repo_root = bucket_mgr.path_for(repo, branch=branch)

            # Build a chunk resolver that reads files relative to repo_root
            def _make_resolver(root: Path):
                def _resolve(ref: str, base_dir: Path | None = None) -> str:
                    search_base = base_dir if base_dir is not None else root
                    candidate = search_base / ref
                    if not candidate.exists():
                        # Try relative to repo root as fallback
                        candidate = root / ref
                    if not candidate.exists():
                        raise FileNotFoundError(
                            f"Chunk not found: {ref!r} (searched under {search_base})"
                        )
                    return candidate.read_text(encoding="utf-8")
                return _resolve

            item_resolver = _make_resolver(repo_root)

            # Read the source file
            source_file = repo_root / source_path
            if not source_file.exists():
                raise FileNotFoundError(
                    f"Source file not found: {source_path!r} in {repo}@{branch}"
                )
            source_text = source_file.read_text(encoding="utf-8")

            # Build item-scoped context
            item_ctx = TemplateContext(
                facts=context.facts,
                groups=context.groups,
                chunk_resolver=item_resolver,
                base_dir=repo_root,
            )

            # Render through template engine
            rendered = render_template(source_text, item_ctx)

            # Determine output path
            suffix = _KIND_SUFFIX.get(kind, f".{kind}.md")
            out_path = output_dir / f"{name}{suffix}"

            if not dry_run:
                out_path.write_text(rendered, encoding="utf-8")

            result.synced.append(name)

        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"{name}: {exc}")

    return result
