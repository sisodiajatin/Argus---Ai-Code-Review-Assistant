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

from app import __version__
from app.config import get_cli_settings
from app.services.vcs.local_git import LocalGitProvider
from app.services.analyzer import ReviewIncompleteError
from app.services.review_pipeline import ReviewPipeline, ReviewResult
from cli.formatters import get_formatter

# Exit codes for `argus review`
EXIT_CRITICAL_FINDINGS = 1
EXIT_REVIEW_FAILED = 2


@click.group(invoke_without_command=True)
@click.version_option(version=__version__, prog_name="argus")
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
    type=click.Choice(["rich", "json", "plain", "sarif"]),
    default=None,
    help="Output format (default: interactive TUI).",
)
@click.option(
    "--model", "-m",
    default=None,
    help="Override AI model (e.g., openai/gpt-oss-120b).",
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
@click.option(
    "--ignore", "-i", "ignore_patterns",
    multiple=True,
    help="Glob pattern to skip (repeatable, or comma-separated). Adds to .argus.yaml 'ignore'.",
)
@click.option(
    "--sarif", "sarif_path",
    default=None,
    type=click.Path(dir_okay=False, writable=True),
    help="Also write findings as SARIF 2.1.0 to this file (for GitHub code scanning).",
)
def review(base, change_type, output_format, model, path, verbose, ignore_patterns, sarif_path):
    """Review code changes using AI.

    Exit codes: 0 = no critical findings, 1 = critical findings,
    2 = the review could not be completed (e.g. the AI provider failed).
    """
    asyncio.run(
        _run_review(
            base, change_type, output_format, model, path, verbose, ignore_patterns, sarif_path
        )
    )


def _write_sarif(sarif_path: str | None, result) -> None:
    """Write the SARIF file, if requested. Only called after a completed review."""
    if not sarif_path:
        return
    import json
    from pathlib import Path

    from app.services.sarif import findings_to_sarif

    Path(sarif_path).write_text(
        json.dumps(findings_to_sarif(result.findings, model=result.model_used), indent=2),
        encoding="utf-8",
    )


def _merge_ignore_patterns(config_patterns: list[str], cli_patterns: tuple[str, ...]) -> list[str]:
    """Combine .argus.yaml ignores with --ignore flags (which may be comma-separated)."""
    merged: list[str] = []
    for raw in [*config_patterns, *cli_patterns]:
        for pattern in str(raw).split(","):
            pattern = pattern.strip()
            if pattern and pattern not in merged:
                merged.append(pattern)
    return merged


async def _run_pipeline_or_exit(settings, pr_files, title, author, base_branch, ignored_paths):
    """Run the review pipeline; exit with EXIT_REVIEW_FAILED if it can't finish.

    A failed review must never print as a clean one, so no results are output.
    """
    try:
        pipeline = ReviewPipeline(settings=settings)
        return await pipeline.run(
            pr_files=pr_files,
            title=title,
            author=author,
            base_branch=base_branch,
            ignored_paths=ignored_paths,
        )
    except ReviewIncompleteError as e:
        click.echo(f"Error: review failed — {e}", err=True)
        click.echo(
            "No results were produced. Check AI_API_KEY, AI_BASE_URL and AI_MODEL "
            "('argus config show').",
            err=True,
        )
        sys.exit(EXIT_REVIEW_FAILED)


async def _run_review(
    base, change_type, output_format, model, path, verbose, ignore_patterns=(), sarif_path=None
):
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

    ignored_paths = _merge_ignore_patterns(repo_config.ignore, ignore_patterns)

    # Determine if TUI mode (default when no --format is specified and stdout is a terminal)
    use_tui = output_format is None and sys.stdout.isatty()

    if use_tui:
        await _run_tui_review(
            settings, base, change_type, model, path, verbose, ignored_paths, sarif_path
        )
    else:
        await _run_plain_review(
            settings, base, change_type, output_format, model, path, verbose, ignored_paths,
            sarif_path,
        )


async def _run_tui_review(
    settings, base, change_type, model, path, verbose, ignored_paths=None, sarif_path=None
):
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
        _write_sarif(sarif_path, ReviewResult())  # empty log keeps upload steps working
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
        result = await _run_pipeline_or_exit(
            settings, pr_files, title, repo_info["author"], base or "main", ignored_paths
        )

    # Save results to dashboard database
    try:
        from cli.db_sync import save_review_to_db
        await save_review_to_db(result, repo_info, title, change_type or "all")
    except Exception as e:  # Don't fail the CLI if DB save fails
        if verbose:
            click.echo(f"Warning: could not save results to dashboard DB: {e}", err=True)

    # Show results
    tui.show_results(result, verbose=verbose)
    _write_sarif(sarif_path, result)

    # Exit with non-zero if critical findings
    critical = sum(1 for f in result.findings if f.severity == "critical")
    if critical > 0:
        sys.exit(EXIT_CRITICAL_FINDINGS)


async def _run_plain_review(
    settings, base, change_type, output_format, model, path, verbose, ignored_paths=None,
    sarif_path=None,
):
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
        click.echo(f"Repository: {repo_info['remote']}", err=True)
        click.echo(f"Branch: {repo_info['branch']}", err=True)
        click.echo(f"Author: {repo_info['author']}", err=True)

    # Get changes
    if verbose:
        click.echo("Fetching changes...", err=True)

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
        if fmt in ("json", "sarif"):
            # Keep stdout machine-readable for CI consumers.
            formatter.print_review(ReviewResult(summary="No changes found to review."))
        else:
            click.echo("No changes found to review.")
        _write_sarif(sarif_path, ReviewResult())  # empty log keeps upload steps working
        sys.exit(0)

    if verbose:
        click.echo(f"Found {len(pr_files)} changed file(s)", err=True)

    # Run review
    if fmt == "rich":
        from rich.console import Console
        console = Console()
        with console.status("[bold blue]Analyzing code with AI...[/bold blue]"):
            result = await _run_pipeline_or_exit(
                settings, pr_files, title, repo_info["author"], base or "main", ignored_paths
            )
    else:
        if verbose:
            click.echo("Analyzing code with AI...", err=True)
        result = await _run_pipeline_or_exit(
            settings, pr_files, title, repo_info["author"], base or "main", ignored_paths
        )

    # Save results to dashboard database
    try:
        from cli.db_sync import save_review_to_db
        await save_review_to_db(result, repo_info, title, change_type or "all")
        if verbose:
            click.echo("Results saved to dashboard database.", err=True)
    except Exception as e:
        if verbose:
            click.echo(f"Warning: Could not save results to dashboard DB: {e}", err=True)

    # Output results
    formatter.print_review(result, verbose=verbose)
    _write_sarif(sarif_path, result)

    # Exit with non-zero if critical findings
    critical = sum(1 for f in result.findings if f.severity == "critical")
    if critical > 0:
        sys.exit(EXIT_CRITICAL_FINDINGS)


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
@click.option("--model", default="openai/gpt-oss-120b", prompt="AI Model", help="Model name.")
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
