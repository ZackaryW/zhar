"""Path helpers for repo-centric harness files and generated context output."""

from __future__ import annotations

from pathlib import Path


def harness_package_root() -> Path:
    """Return the package directory for the zhar harness helpers."""
    return Path(__file__).resolve().parent


def harness_files_root(base_dir: Path | None = None) -> Path:
    """Return the mirrored harness-files directory used by runtime lookups."""
    return Path(base_dir) if base_dir is not None else harness_package_root() / "files"


def default_harness_install_path(kind: str, source_path: Path) -> Path:
    """Return the default workspace destination for a mirrored harness file."""
    github_root = Path(".github")

    if kind == "agent":
        return github_root / "agents" / source_path.name
    if kind == "instruction":
        return github_root / "instructions" / source_path.name
    if kind == "skill":
        return github_root / "skills" / source_path.parent.name / source_path.name

    raise ValueError(f"Unsupported harness kind: {kind}")


def default_context_output_path() -> Path:
    """Return the default path for generated legacy memory-context output."""
    return Path(".github") / "agents" / "zhar-context.agent.md"