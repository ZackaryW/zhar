"""Agent-related CLI commands: install, uninstall, and get."""

from __future__ import annotations

from pathlib import Path

import click

from zhar.cli.common import open_store
from zhar.mem.query import Query
from zhar.parser.render import ParseContext, render
from zhar.stack.bucket import BucketManager
from zhar.stack.registry import StackRegistry
from zhar.utils.facts import load_effective_facts, project_facts_path


@click.group(name="agent")
@click.pass_context
def agent_group(ctx: click.Context) -> None:
    """Manage agent, instruction, skill, and hook items."""


@agent_group.command("get")
@click.argument("name")
@click.option(
    "--cache-dir",
    default=None,
    type=click.Path(),
    metavar="DIR",
    help="Override the bucket cache directory (default: ~/.zhar/stack/).",
)
@click.pass_context
def agent_get(ctx: click.Context, name: str, cache_dir: str | None) -> None:
    """Render a named installed item from source with current workspace facts.

    Unlike ``zhar stack sync`` (which writes to disk and leaves
    ``%%ZHAR.RSKILL%%`` tokens verbatim in agent/instruction/hook files),
    ``agent get`` always resolves skills inline and prints the result to
    stdout.  This gives an up-to-date, fully compiled view of any installed
    item against the live workspace facts.
    """
    _, zhar_root = open_store(ctx.obj["root"])

    reg = StackRegistry(zhar_root / "cfg" / "stack.json")
    entry = reg.get(name)
    if entry is None:
        raise click.ClickException(f"No installed item named {name!r}.")

    bm_kwargs: dict = {}
    if cache_dir is not None:
        bm_kwargs["cache_dir"] = Path(cache_dir)
    bm = BucketManager(**bm_kwargs)

    repo = entry["repo"]
    branch = entry["branch"]
    source_path = entry["source_path"]

    try:
        repo_root = bm.path_for(repo, branch=branch)
    except FileNotFoundError:
        raise click.ClickException(
            f"Bucket {repo!r}@{branch} not in cache. Run: zhar stack bucket add {repo}"
        )

    source_file = repo_root / source_path
    if not source_file.exists():
        raise click.ClickException(
            f"Source file not found: {source_path!r} in {repo}@{branch}"
        )

    # Build current-workspace facts + memory context
    facts = load_effective_facts(project_facts_path(zhar_root))
    store, _ = open_store(ctx.obj["root"])
    groups = {g: store.query(Query(groups=[g])) for g in store.groups}

    def _resolver(ref: str, base_dir: Path | None = None) -> str:
        search = base_dir if base_dir is not None else repo_root
        candidate = search / ref
        if not candidate.exists():
            candidate = repo_root / ref
        if not candidate.exists():
            raise FileNotFoundError(f"Chunk not found: {ref!r}")
        return candidate.read_text(encoding="utf-8")

    context = ParseContext(
        facts=facts,
        groups=groups,
        chunk_resolver=_resolver,
        base_dir=repo_root,
        # RSKILL tokens are always left verbatim on `agent get` — the caller
        # sees the skill references explicitly.  Only RCHUNK is expanded inline.
        # (sync with kind=="skill" is the only place RSKILL expands eagerly.)
        expand_skills=False,
    )

    rendered = render(source_file.read_text(encoding="utf-8"), context)
    click.echo(rendered, nl=False)


def register_agent_commands(cli_group: click.Group) -> None:
    """Register the agent command group on *cli_group*."""
    cli_group.add_command(agent_group)
