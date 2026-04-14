"""sync_stack — render and write installed stack items to an output directory."""
# %ZHAR:238d% %ZHAR:2a6b%
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from zhar.parser import TemplateContext
from zhar.stack.render import render_installed_item

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

        try:
            rendered = render_installed_item(
                registry,
                bucket_mgr,
                name,
                facts=context.facts,
                groups=context.groups,
                expand_skills=(kind == "skill"),
            )

            suffix = _KIND_SUFFIX.get(kind, f".{kind}.md")
            out_path = output_dir / f"{name}{suffix}"
            if not dry_run:
                out_path.write_text(rendered.rendered, encoding="utf-8")

            result.synced.append(name)
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"{name}: {exc}")

    return result