"""sync_stack — render and write installed stack items to an output directory."""
# %ZHAR:238d% %ZHAR:2a6b%
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from zhar.parser import TemplateContext, render_template

if TYPE_CHECKING:
    from zhar.stack.bucket import BucketManager
    from zhar.stack.registry import StackRegistry


_KIND_SUFFIX: dict[str, str] = {
    "agent": ".agent.md",
    "instruction": ".instructions.md",
    "skill": ".skill.md",
    "hook": ".hook.md",
}


@dataclass
class SyncResult:
    """Summary of a ``sync_stack`` run."""

    synced: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Return the total number of processed items."""
        return len(self.synced) + len(self.skipped) + len(self.errors)


def sync_stack(
    registry: "StackRegistry",
    bucket_mgr: "BucketManager",
    context: TemplateContext,
    output_dir: Path,
    *,
    dry_run: bool = False,
) -> SyncResult:
    """Render all installed stack items and write them to *output_dir*."""
    result = SyncResult()
    output_dir.mkdir(parents=True, exist_ok=True)

    for item in registry.list_items():
        name = item["name"]
        kind = item["kind"]
        repo = item["repo"]
        branch = item["branch"]
        source_path = item["source_path"]

        try:
            repo_root = bucket_mgr.path_for(repo, branch=branch)

            def _make_resolver(root: Path):
                def _resolve(ref: str, base_dir: Path | None = None) -> str:
                    search_base = base_dir if base_dir is not None else root
                    candidate = search_base / ref
                    if not candidate.exists():
                        candidate = root / ref
                    if not candidate.exists():
                        raise FileNotFoundError(
                            f"Chunk not found: {ref!r} (searched under {search_base})"
                        )
                    return candidate.read_text(encoding="utf-8")

                return _resolve

            source_file = repo_root / source_path
            if not source_file.exists():
                raise FileNotFoundError(
                    f"Source file not found: {source_path!r} in {repo}@{branch}"
                )

            item_ctx = TemplateContext(
                facts=context.facts,
                groups=context.groups,
                chunk_resolver=_make_resolver(repo_root),
                base_dir=repo_root,
                # Skills eagerly expand nested RSKILL tokens; all other kinds
                # leave them verbatim for runtime resolution via `zhar agent get`
                expand_skills=(kind == "skill"),
            )
            rendered = render_template(source_file.read_text(encoding="utf-8"), item_ctx)

            suffix = _KIND_SUFFIX.get(kind, f".{kind}.md")
            out_path = output_dir / f"{name}{suffix}"
            if not dry_run:
                out_path.write_text(rendered, encoding="utf-8")

            result.synced.append(name)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"{name}: {exc}")

    return result