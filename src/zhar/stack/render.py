"""Helpers for rendering installed stack items from bucket sources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from rapidfuzz import fuzz, process

from zhar.parser.render import ParseContext, render

if TYPE_CHECKING:
    from zhar.stack.bucket import BucketManager
    from zhar.stack.registry import StackRegistry


@dataclass(frozen=True)
class RenderedStackItem:
    """Rendered output and metadata for one installed stack item."""

    name: str
    kind: str
    rendered: str


@dataclass(frozen=True)
class CachedStackSource:
    """One fetchable stack source discovered in a cached bucket repo."""

    repo: str
    branch: str
    kind: str
    name: str
    qualified_name: str
    source_path: str
    repo_root: Path


def make_repo_chunk_resolver(repo_root: Path) -> Callable[[str, Path | None], str]:
    """Return a resolver that loads chunk references from *repo_root*."""

    def _resolve(ref: str, base_dir: Path | None = None) -> str:
        """Resolve *ref* relative to *base_dir* or fall back to *repo_root*."""
        search_base = base_dir if base_dir is not None else repo_root
        candidate = search_base / ref
        if not candidate.exists():
            candidate = repo_root / ref
        if not candidate.exists():
            raise FileNotFoundError(
                f"Chunk not found: {ref!r} (searched under {search_base})"
            )
        return candidate.read_text(encoding="utf-8")

    return _resolve


def _strip_known_suffix(filename: str, suffix: str) -> str:
    """Return *filename* without *suffix* when the suffix is present."""
    if filename.endswith(suffix):
        return filename[: -len(suffix)]
    return Path(filename).stem


def _candidate_display_names(candidates: list[CachedStackSource]) -> dict[str, str]:
    """Return the preferred display label for each cached-source path."""
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.name] = counts.get(candidate.name, 0) + 1

    labels: dict[str, str] = {}
    for candidate in candidates:
        labels[candidate.source_path] = (
            candidate.name
            if counts[candidate.name] == 1
            else candidate.qualified_name
        )
    return labels


def discover_cached_stack_sources(bucket_mgr: "BucketManager") -> list[CachedStackSource]:
    """Discover fetchable stack sources across every cached bucket repo."""
    candidates: list[CachedStackSource] = []
    seen_paths: set[tuple[str, str, str]] = set()

    def _add_candidate(
        repo: str,
        branch: str,
        kind: str,
        name: str,
        path: Path,
        repo_root: Path,
    ) -> None:
        """Append one cached source candidate if it has not been seen yet."""
        source_path = path.relative_to(repo_root).as_posix()
        key = (repo, branch, source_path)
        if key in seen_paths:
            return
        seen_paths.add(key)
        candidates.append(
            CachedStackSource(
                repo=repo,
                branch=branch,
                kind=kind,
                name=name,
                qualified_name=f"{repo}:{name}",
                source_path=source_path,
                repo_root=repo_root,
            )
        )

    for entry in bucket_mgr.list_repos():
        repo = entry["repo"]
        branch = entry["branch"]
        repo_root = Path(entry["local_path"])

        for path in sorted((repo_root / ".github" / "agents").glob("*.agent.md")):
            _add_candidate(repo, branch, "agent", _strip_known_suffix(path.name, ".agent.md"), path, repo_root)
        for path in sorted((repo_root / ".github" / "instructions").glob("*.instructions.md")):
            _add_candidate(repo, branch, "instruction", _strip_known_suffix(path.name, ".instructions.md"), path, repo_root)
        for path in sorted((repo_root / ".github" / "skills").glob("*/SKILL.md")):
            _add_candidate(repo, branch, "skill", path.parent.name, path, repo_root)
        for path in sorted((repo_root / ".github" / "hooks").glob("*.hook.md")):
            _add_candidate(repo, branch, "hook", _strip_known_suffix(path.name, ".hook.md"), path, repo_root)

        for path in sorted((repo_root / "agents").glob("*")):
            if path.is_file():
                _add_candidate(repo, branch, "agent", path.stem, path, repo_root)
        for path in sorted((repo_root / "instructions").glob("*")):
            if path.is_file():
                _add_candidate(repo, branch, "instruction", path.stem, path, repo_root)
        for path in sorted((repo_root / "skills").glob("*")):
            if path.is_file():
                _add_candidate(repo, branch, "skill", path.stem, path, repo_root)
        for path in sorted((repo_root / "skills").glob("*/SKILL.md")):
            _add_candidate(repo, branch, "skill", path.parent.name, path, repo_root)
        for path in sorted((repo_root / "hooks").glob("*")):
            if path.is_file():
                _add_candidate(repo, branch, "hook", path.stem, path, repo_root)

    return candidates


def resolve_cached_stack_source(
    bucket_mgr: "BucketManager",
    requested_name: str,
    *,
    fuzzy_conf: float | None = None,
) -> CachedStackSource:
    """Resolve *requested_name* to a cached stack source, optionally using fuzzy matching."""
    candidates = discover_cached_stack_sources(bucket_mgr)
    if not candidates:
        raise KeyError("No cached stack sources found. Run: zhar stack bucket add <repo>")

    display_names = _candidate_display_names(candidates)
    exact_matches = [
        candidate
        for candidate in candidates
        if requested_name in {
            candidate.name,
            candidate.qualified_name,
            candidate.source_path,
            display_names[candidate.source_path],
        }
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        options = ", ".join(sorted(candidate.qualified_name for candidate in exact_matches))
        raise KeyError(
            f"Cached stack source {requested_name!r} is ambiguous. Matches: {options}."
        )

    if fuzzy_conf is None:
        raise KeyError(f"No cached stack source matched {requested_name!r}.")

    choices = [display_names[candidate.source_path] for candidate in candidates]
    match = process.extractOne(requested_name, choices, scorer=fuzz.WRatio)
    if match is None:
        raise KeyError(f"No cached stack source matched {requested_name!r}.")

    matched_label, raw_score, choice_index = match
    score = raw_score / 100.0
    if score < fuzzy_conf:
        raise KeyError(
            f"No cached stack source matched {requested_name!r}. "
            f"Top fuzzy match {matched_label!r} scored {score:.3f}, "
            f"below --fuzzy-conf {fuzzy_conf:.3f}."
        )

    return candidates[choice_index]


def render_installed_item(
    registry: "StackRegistry",
    bucket_mgr: "BucketManager",
    name: str,
    *,
    facts: dict[str, str],
    groups: dict[str, Any],
    expand_skills: bool | None = None,
) -> RenderedStackItem:
    """Render one installed stack item against the provided workspace context."""
    entry = registry.get(name)
    if entry is None:
        raise KeyError(f"No installed item named {name!r}.")

    repo = entry["repo"]
    branch = entry["branch"]
    kind = entry["kind"]
    source_path = entry["source_path"]

    try:
        repo_root = bucket_mgr.path_for(repo, branch=branch)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Bucket {repo!r}@{branch} not in cache. Run: zhar stack bucket add {repo}"
        ) from exc

    source_file = repo_root / source_path
    if not source_file.exists():
        raise FileNotFoundError(
            f"Source file not found: {source_path!r} in {repo}@{branch}"
        )

    context = ParseContext(
        facts=dict(facts),
        groups=groups,
        chunk_resolver=make_repo_chunk_resolver(repo_root),
        base_dir=repo_root,
        expand_skills=kind == "skill" if expand_skills is None else expand_skills,
    )
    rendered = render(source_file.read_text(encoding="utf-8"), context)
    return RenderedStackItem(name=name, kind=kind, rendered=rendered)


def render_cached_stack_source(
    source: CachedStackSource,
    *,
    facts: dict[str, str],
    groups: dict[str, Any],
    expand_skills: bool = False,
) -> RenderedStackItem:
    """Render one cached stack source against the provided workspace context."""
    source_file = source.repo_root / source.source_path
    if not source_file.exists():
        raise FileNotFoundError(
            f"Source file not found: {source.source_path!r} in {source.repo}@{source.branch}"
        )

    context = ParseContext(
        facts=dict(facts),
        groups=groups,
        chunk_resolver=make_repo_chunk_resolver(source.repo_root),
        base_dir=source.repo_root,
        expand_skills=expand_skills,
    )
    rendered = render(source_file.read_text(encoding="utf-8"), context)
    return RenderedStackItem(name=source.name, kind=source.kind, rendered=rendered)