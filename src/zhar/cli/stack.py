"""Stack-related CLI commands for zhar."""

from __future__ import annotations

from pathlib import Path

import click

from zhar.cli.common import open_store
from zhar.mem.query import Query
from zhar.stack.bucket import BucketManager
from zhar.stack.registry import StackRegistry
from zhar.stack.sync import sync_stack
from zhar.parser import TemplateContext
from zhar.utils.facts import load_effective_facts, project_facts_path


# %ZHAR:7e64% %ZHAR:fabe%
def stack_helpers(ctx: click.Context) -> tuple[StackRegistry, BucketManager, Path]:
    """Resolve registry, bucket manager, and zhar root for stack commands."""
    _, zhar_root = open_store(ctx.obj["root"])
    return StackRegistry(zhar_root / "cfg" / "stack.json"), BucketManager(), zhar_root


@click.group(name="stack")
@click.pass_context
def stack_group(ctx: click.Context) -> None:
    """Manage stack buckets and installed template items."""


@stack_group.group("bucket")
@click.pass_context
def stack_bucket_group(ctx: click.Context) -> None:
    """Manage GitHub repo buckets in the local cache."""


@stack_bucket_group.command("add")
@click.argument("repo")
@click.option("--branch", default="main", show_default=True, help="Branch to clone or pull.")
@click.pass_context
def stack_bucket_add(ctx: click.Context, repo: str, branch: str) -> None:
    """Add or refresh a bucket from GitHub."""
    _, bucket_manager, _ = stack_helpers(ctx)
    click.echo(f"Fetching {repo}@{branch} …")
    click.echo(f"Cached at: {bucket_manager.add(repo, branch=branch)}")


@stack_bucket_group.command("list")
@click.pass_context
def stack_bucket_list(ctx: click.Context) -> None:
    """List cached buckets."""
    _, bucket_manager, _ = stack_helpers(ctx)
    repos = bucket_manager.list_repos()
    if not repos:
        click.echo("(no buckets cached)")
        return
    for repo in repos:
        click.echo(f"{repo['repo']}  branch={repo['branch']}  path={repo['local_path']}")


@stack_bucket_group.command("remove")
@click.argument("repo")
@click.option("--branch", default=None, help="Specific branch (default: all).")
@click.pass_context
def stack_bucket_remove(ctx: click.Context, repo: str, branch: str | None) -> None:
    """Remove a cached bucket."""
    _, bucket_manager, _ = stack_helpers(ctx)
    if bucket_manager.remove(repo, branch=branch):
        click.echo(f"Removed: {repo}")
        return
    click.echo(f"Not found: {repo}")


@stack_group.command("install")
@click.argument("name")
@click.argument("repo")
@click.option("--branch", default="main", show_default=True)
@click.option("--kind", required=True, type=click.Choice(["agent", "instruction", "skill", "hook"]), help="Kind of item to install.")
@click.option("--source", "source_path", required=True, metavar="PATH", help="Relative path within the repo to the source file.")
@click.pass_context
def stack_install(
    ctx: click.Context,
    name: str,
    repo: str,
    branch: str,
    kind: str,
    source_path: str,
) -> None:
    """Install an item from a bucket repo into this project."""
    registry, bucket_manager, _ = stack_helpers(ctx)
    bucket_manager.add(repo, branch=branch)
    registry.install(name, repo=repo, branch=branch, kind=kind, source_path=source_path)
    click.echo(f"Installed {name!r} ({kind}) from {repo}@{branch}:{source_path}")


@stack_group.command("uninstall")
@click.argument("name")
@click.pass_context
def stack_uninstall(ctx: click.Context, name: str) -> None:
    """Remove an installed item from the registry."""
    registry, _, _ = stack_helpers(ctx)
    if registry.uninstall(name):
        click.echo(f"Uninstalled: {name}")
        return
    click.echo(f"Not found: {name}")


@stack_group.command("list")
@click.pass_context
def stack_list(ctx: click.Context) -> None:
    """List all installed stack items."""
    registry, _, _ = stack_helpers(ctx)
    items = registry.list_items()
    if not items:
        click.echo("(no items installed)")
        return
    for item in items:
        click.echo(
            f"{item['name']}  kind={item['kind']}  "
            f"repo={item['repo']}@{item['branch']}  "
            f"source={item['source_path']}"
        )


@stack_group.command("sync")
@click.option("--out", default=None, type=click.Path(), metavar="DIR", help="Output directory (default: .github/agents/).")
@click.option("--dry-run", is_flag=True, default=False, help="Render but do not write files.")
@click.pass_context
def stack_sync_command(ctx: click.Context, out: str | None, dry_run: bool) -> None:
    """Render all installed stack items and write them to the output directory."""
    registry, bucket_manager, zhar_root = stack_helpers(ctx)
    output_dir = Path(out) if out else Path(".github") / "agents"
    output_dir.mkdir(parents=True, exist_ok=True)

    facts_data = load_effective_facts(project_facts_path(zhar_root))
    store, _ = open_store(ctx.obj["root"])
    groups_data = {
        group_name: store.query(Query(groups=[group_name]))
        for group_name in store.groups
    }
    result = sync_stack(
        registry,
        bucket_manager,
        TemplateContext(facts=facts_data, groups=groups_data, chunk_resolver=None),
        output_dir,
        dry_run=dry_run,
    )

    for name in result.synced:
        action = "would write" if dry_run else "wrote"
        click.echo(f"  {action}: {name}")
    for error in result.errors:
        click.echo(f"  ERROR: {error}", err=True)
    click.echo(f"\n{'(dry run) ' if dry_run else ''}synced={len(result.synced)} errors={len(result.errors)}")


def register_stack_commands(cli_group: click.Group) -> None:
    """Register the stack command group on *cli_group*."""
    cli_group.add_command(stack_group)