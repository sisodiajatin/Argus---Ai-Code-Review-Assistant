"""CLI entry point for Argus — The All-Seeing Code Reviewer.

Usage:
    argus                               # Interactive TUI review
    argus review                        # Review uncommitted changes
    argus review --base main            # Compare current branch to main
    argus review --type staged          # Review only staged changes
    argus review --format json          # Output as JSON (no TUI)
    argus config show                   # Show current config
    argus config init                   # Set up global config
"""

import asyncio
import sys

import click

from app.config import CLISettings, get_cli_settings
from app.services.vcs.local_git import LocalGitProvider
from app.services.review_pipeline import ReviewPipeline
from cli.formatters import get_formatter


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="argus")
@click.pass_context
def cli(ctx):
    """Argus — The All-Seeing Code Reviewer."""
    if ctx.invoked_subcommand is None:
        # No subcommand → launch interactive TUI review
        ctx.invoke(review)


@cli.command()
@click.option(
    "--base", "-b",
    default=None,
    help="Base branch to compare against (e.g., main, develop).",
)
@click.option(
    "--type", "-t", "change_type",
    type=click.Choice(["all", "staged", "committed"]),
    default="all",
    help="Type of changes to review.",
)
@click.option(
    "--format", "-f", "output_format",
    type=click.Choice(["rich", "json", "plain"]),
    default=None,
    help="Output format (default: interactive TUI).",
)
@click.option(
    "--model", "-m",
    default=None,
    help="Override AI model (e.g., llama-3.3-70b-versatile).",
)
@click.option(
    "--path", "-p",
    default=".",
    help="Path to the git repository.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Show verbose output.",
)
def review(base, change_type, output_format, model, path, verbose):
    """Review code changes using AI."""
    asyncio.run(_run_review(base, change_type, output_format, model, path, verbose))


async def _run_review(base, change_type, output_format, model, path, verbose):
    """Async implementation of the review command."""
    from cli.config_file import load_repo_config

    # Load .argus.yaml from repo (if it exists)
    repo_config = load_repo_config(path)

    # Load settings — precedence: CLI flags > .argus.yaml > env defaults
    settings = get_cli_settings()
    if model:
        settings.ai_model = model
    elif repo_config.model:
        settings.ai_model = repo_config.model
    if output_format:
        settings.output_format = output_format

    # Apply yaml defaults when CLI flags are at their defaults
    if base is None and repo_config.base_branch:
        base = repo_config.base_branch
    if change_type == "all" and repo_config.review_type:
        change_type = repo_config.review_type

    # Apply focus and severity_threshold from .argus.yaml
    if repo_config.focus and not settings.review_focus:
        settings.review_focus = repo_config.focus
    if repo_config.severity_threshold and settings.severity_threshold == "suggestion":
        settings.severity_threshold = repo_config.severity_threshold

    # Check API key
    if not settings.ai_api_key:
        click.echo("Error: No AI API key configured.", err=True)
        click.echo("Run 'argus config init' to set up your API key.", err=True)
        sys.exit(1)

    # Determine if TUI mode (default when no --format is specified and stdout is a terminal)
    use_tui = output_format is None and sys.stdout.isatty()

    if use_tui:
        await _run_tui_review(settings, base, change_type, model, path, verbose)
    else:
        await _run_plain_review(settings, base, change_type, output_format, model, path, verbose)


async def _run_tui_review(settings, base, change_type, model, path, verbose):
    """Run review with the interactive TUI."""
    from cli.tui import ArgusTUI

    tui = ArgusTUI()

    # Connect to local git
    try:
        git = LocalGitProvider(repo_path=path)
    except ValueError as e:
        tui.show_error(str(e))
        sys.exit(1)

    repo_info = git.get_repo_info()

    # Get changes
    if base:
        pr_files = git.get_branch_diff(base)
        review_type = f"vs {base}"
        title = f"Branch diff: {repo_info['branch']} vs {base}"
    elif change_type == "staged":
        pr_files = git.get_staged_changes()
        review_type = "staged changes"
        title = f"Staged changes on {repo_info['branch']}"
    elif change_type == "committed":
        pr_files = git.get_committed_changes(base or "main")
        review_type = "committed changes"
        title = f"Committed changes on {repo_info['branch']}"
    else:
        pr_files = git.get_uncommitted_changes()
        review_type = "uncommitted changes"
        title = f"Uncommitted changes on {repo_info['branch']}"

    if not pr_files:
        tui.show_welcome(repo_info, 0, 0, 0, review_type)
        tui.show_no_changes()
        sys.exit(0)

    # Calculate stats
    total_additions = sum(f.additions for f in pr_files)
    total_deletions = sum(f.deletions for f in pr_files)

    # Show welcome screen
    tui.show_welcome(repo_info, len(pr_files), total_additions, total_deletions, review_type)

    # Wait for user action
    action = tui.wait_for_action()
    if action == "quit":
        tui.cleanup()
        sys.exit(0)
    if action == "config":
        tui.cleanup()
        click.echo("Run 'argus config show' or 'argus config init'")
        sys.exit(0)

    # Run the review with progress animation
    with tui.show_reviewing():
        pipeline = ReviewPipeline(settings=settings)
        result = await pipeline.run(
            pr_files=pr_files,
            title=title,
            author=repo_info["author"],
            base_branch=base or "main",
        )

    # Save results to dashboard database
    try:
        from cli.db_sync import save_review_to_db
        await save_review_to_db(result, repo_info, title, change_type or "all")
    except Exception:
        pass  # Don't fail the CLI if DB save fails

    # Show results
    tui.show_results(result, verbose=verbose)

    # Exit with non-zero if critical findings
    critical = sum(1 for f in result.findings if f.severity == "critical")
    if critical > 0:
        sys.exit(1)


async def _run_plain_review(settings, base, change_type, output_format, model, path, verbose):
    """Run review with traditional formatter output (no TUI)."""
    # Get the formatter
    fmt = output_format or settings.output_format
    formatter = get_formatter(fmt)

    # Connect to local git
    try:
        git = LocalGitProvider(repo_path=path)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    repo_info = git.get_repo_info()
    if verbose:
        click.echo(f"Repository: {repo_info['remote']}")
        click.echo(f"Branch: {repo_info['branch']}")
        click.echo(f"Author: {repo_info['author']}")

    # Get changes
    if verbose:
        click.echo("Fetching changes...")

    if base:
        pr_files = git.get_branch_diff(base)
        title = f"Branch diff: {repo_info['branch']} vs {base}"
    elif change_type == "staged":
        pr_files = git.get_staged_changes()
        title = f"Staged changes on {repo_info['branch']}"
    elif change_type == "committed":
        pr_files = git.get_committed_changes(base or "main")
        title = f"Committed changes on {repo_info['branch']}"
    else:
        pr_files = git.get_uncommitted_changes()
        title = f"Uncommitted changes on {repo_info['branch']}"

    if not pr_files:
        click.echo("No changes found to review.")
        sys.exit(0)

    if verbose:
        click.echo(f"Found {len(pr_files)} changed file(s)")

    # Run review
    if fmt == "rich":
        from rich.console import Console
        console = Console()
        with console.status("[bold blue]Analyzing code with AI...[/bold blue]"):
            pipeline = ReviewPipeline(settings=settings)
            result = await pipeline.run(
                pr_files=pr_files,
                title=title,
                author=repo_info["author"],
                base_branch=base or "main",
            )
    else:
        if verbose:
            click.echo("Analyzing code with AI...")
        pipeline = ReviewPipeline(settings=settings)
        result = await pipeline.run(
            pr_files=pr_files,
            title=title,
            author=repo_info["author"],
            base_branch=base or "main",
        )

    # Save results to dashboard database
    try:
        from cli.db_sync import save_review_to_db
        await save_review_to_db(result, repo_info, title, change_type or "all")
        if verbose:
            click.echo("Results saved to dashboard database.")
    except Exception:
        if verbose:
            click.echo("Warning: Could not save results to dashboard DB.")

    # Output results
    formatter.print_review(result, verbose=verbose)

    # Exit with non-zero if critical findings
    critical = sum(1 for f in result.findings if f.severity == "critical")
    if critical > 0:
        sys.exit(1)


@cli.group()
def config():
    """Manage Argus configuration."""
    pass


@config.command("show")
def config_show():
    """Show current configuration."""
    from pathlib import Path
    settings = get_cli_settings()
    global_env = Path.home() / ".codereview" / ".env"
    click.echo("Argus Configuration:")
    click.echo(f"  AI Model:     {settings.ai_model}")
    click.echo(f"  AI Base URL:  {settings.ai_base_url}")
    click.echo(f"  AI API Key:   {'***' + settings.ai_api_key[-4:] if settings.ai_api_key else 'NOT SET'}")
    click.echo(f"  Database:     {settings.database_url}")
    click.echo(f"  Output:       {settings.output_format}")
    click.echo(f"  Max files:    {settings.max_files_per_review}")
    click.echo(f"  Chunk limit:  {settings.chunk_token_limit} tokens")
    click.echo(f"  Global config: {global_env} ({'exists' if global_env.exists() else 'not found'})")


@config.command("init")
@click.option("--api-key", prompt="AI API Key", help="Your AI provider API key.")
@click.option("--model", default="llama-3.3-70b-versatile", prompt="AI Model", help="Model name.")
@click.option(
    "--base-url",
    default="https://api.groq.com/openai/v1",
    prompt="AI Base URL",
    help="Base URL for the OpenAI-compatible API.",
)
def config_init(api_key, model, base_url):
    """Set up global config at ~/.codereview/.env (works from any directory)."""
    from pathlib import Path
    config_dir = Path.home() / ".codereview"
    config_dir.mkdir(exist_ok=True)
    env_file = config_dir / ".env"
    env_file.write_text(
        f"# Argus CLI Configuration\n"
        f"AI_API_KEY={api_key}\n"
        f"AI_MODEL={model}\n"
        f"AI_BASE_URL={base_url}\n"
    )
    click.echo(f"Config saved to {env_file}")
    click.echo("You can now run 'argus' from any git repo.")


@config.command("init-repo")
@click.option("--path", "-p", default=".", help="Path to the git repository.")
def config_init_repo(path):
    """Create a starter .argus.yaml in a repo."""
    from cli.config_file import create_starter_config
    config_path = create_starter_config(path)
    click.echo(f"Created {config_path}")
    click.echo("Edit this file to customize Argus for this repo.")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
