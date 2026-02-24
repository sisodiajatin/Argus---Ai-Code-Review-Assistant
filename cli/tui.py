"""Interactive Terminal UI for Argus.

Provides a full-screen CodeRabbit-like experience with:
- Animated ASCII art banner
- Repository info display
- Live review progress
- Interactive results navigation
"""

import io
import os
import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.align import Align
from rich.columns import Columns
from rich.live import Live
from rich.spinner import Spinner
from rich.layout import Layout
from rich.box import HEAVY, ROUNDED, SIMPLE, DOUBLE

from cli.banner import (
    ARGUS_LOGO,
    GRADIENT_COLORS,
    TAGLINE,
    SEVERITY_COLORS,
    CATEGORY_LABELS,
    PRIMARY,
    SECONDARY,
    ACCENT,
    DIM_TEXT,
    BORDER_COLOR,
    render_logo,
    render_tagline,
    render_mini_logo,
)
from app.services.review_pipeline import ReviewResult


def _make_console() -> Console:
    """Create a Console that handles Windows encoding."""
    if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
        wrapper = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        console = Console(file=wrapper, force_terminal=True)
        console._argus_wrapper = wrapper  # prevent GC closing it
        return console
    return Console()


def _detach_console(console: Console):
    """Safely detach the wrapper to avoid closing stdout."""
    wrapper = getattr(console, "_argus_wrapper", None)
    if wrapper is not None:
        try:
            wrapper.detach()
        except Exception:
            pass


class ArgusTUI:
    """Full-screen terminal UI for Argus code review."""

    def __init__(self):
        self.console = _make_console()
        self.width = min(self.console.width, 90)

    def _center(self, renderable) -> Align:
        return Align.center(renderable, width=self.width)

    def show_welcome(
        self,
        repo_info: dict,
        file_count: int,
        additions: int,
        deletions: int,
        review_type: str = "uncommitted changes",
    ):
        """Display the welcome screen with banner and repo info."""
        self.console.clear()
        self.console.print()

        # Logo
        self.console.print(self._center(render_logo()))
        self.console.print()
        self.console.print(self._center(render_tagline()))
        self.console.print()

        # Repo info
        remote = repo_info.get("remote", "local")
        branch = repo_info.get("branch", "unknown")

        repo_display = remote
        if repo_display.endswith(".git"):
            repo_display = repo_display[:-4]
        if "github.com/" in repo_display:
            repo_display = repo_display.split("github.com/")[-1]
        elif "github.com:" in repo_display:
            repo_display = repo_display.split("github.com:")[-1]

        info_text = Text()
        info_text.append("    repo: ", style=DIM_TEXT)
        info_text.append(repo_display, style=f"bold {PRIMARY}")
        self.console.print(self._center(info_text))

        branch_text = Text()
        branch_text.append("    branch: ", style=DIM_TEXT)
        branch_text.append(branch, style=f"bold white")
        branch_text.append(f"  ({review_type})", style=DIM_TEXT)
        self.console.print(self._center(branch_text))

        self.console.print()

        # File stats
        added = 0
        modified = 0
        for _ in range(file_count):
            pass  # We just use the total count

        stats_lines = []

        line1 = Text()
        line1.append("    \u25A0 ", style=f"bold {PRIMARY}")
        line1.append(f"{file_count} files changed", style="bold white")
        stats_lines.append(line1)

        line2 = Text()
        line2.append("    \u251C\u2500\u2500 ", style=DIM_TEXT)
        line2.append(f"+{additions}", style="bold #22C55E")
        line2.append(" insertions / ", style=DIM_TEXT)
        line2.append(f"-{deletions}", style="bold #EF4444")
        line2.append(" deletions", style=DIM_TEXT)
        stats_lines.append(line2)

        for line in stats_lines:
            self.console.print(self._center(line))

        self.console.print()
        self.console.print()

        # Action prompt
        prompt = Text()
        prompt.append("         Hit ", style=DIM_TEXT)
        prompt.append("Enter", style=f"bold {PRIMARY}")
        prompt.append(" to start the review", style=DIM_TEXT)
        self.console.print(self._center(prompt))

        quit_text = Text()
        quit_text.append("         Hit ", style=DIM_TEXT)
        quit_text.append("Q", style=f"bold {PRIMARY}")
        quit_text.append(" to quit", style=DIM_TEXT)
        self.console.print(self._center(quit_text))

        self.console.print()

        # Status bar
        self._print_status_bar("Enter: Review | Q: Quit | C: Config")

    def _print_status_bar(self, text: str):
        """Print a styled bottom status bar."""
        bar = Table(show_header=False, box=None, padding=0, expand=True)
        bar.add_column(ratio=1)
        bar.add_column(justify="right", width=20)

        left = Text(f" {text}", style=f"bold white on #1A1A2E")
        right = Text()
        right.append(" \u25C9 ", style=f"bold {PRIMARY} on #1A1A2E")
        right.append("argus ", style=f"bold {GRADIENT_COLORS[2]} on #1A1A2E")

        bar.add_row(left, right)
        self.console.print(bar)

    def wait_for_action(self) -> str:
        """Wait for user keypress. Returns 'review', 'quit', or 'config'."""
        try:
            import click
            while True:
                char = click.getchar()
                if char in ("\r", "\n"):
                    return "review"
                if char.lower() == "q":
                    return "quit"
                if char.lower() == "c":
                    return "config"
        except (KeyboardInterrupt, EOFError):
            return "quit"

    def show_reviewing(self) -> Live:
        """Show the animated review progress. Returns the Live context."""
        self.console.print()

        header = Text()
        header.append("  \u25C9 ", style=f"bold {PRIMARY}")
        header.append("Analyzing code with AI", style="bold white")
        header.append("...", style=DIM_TEXT)
        self.console.print(header)
        self.console.print()

        # Return a spinner we can use
        return self.console.status(
            f"[bold {PRIMARY}]  Running review pipeline...[/]",
            spinner="dots",
            spinner_style=f"bold {PRIMARY}",
        )

    def show_results(self, result: ReviewResult, verbose: bool = False):
        """Display review results in the Argus style."""
        self.console.print()

        # Header
        header = render_mini_logo()
        header.append(" Review Complete", style="bold white")
        self.console.print(Rule(header, style=SECONDARY))
        self.console.print()

        # Stats
        stats = Table(show_header=False, box=None, padding=(0, 2))
        stats.add_column(style=f"bold {DIM_TEXT}")
        stats.add_column(style="bold white")
        stats.add_row("Files", str(result.files_reviewed))
        stats.add_row("Chunks", str(result.chunks_processed))
        stats.add_row("Model", result.model_used)
        stats.add_row("Tokens", f"{result.tokens_used:,}")
        stats.add_row("Time", f"{result.processing_time_ms:.0f}ms")
        self.console.print(
            Panel(stats, border_style=BORDER_COLOR, title="[bold white]Stats[/]", title_align="left")
        )

        # PR Description (what the changes do)
        if result.pr_description:
            self.console.print()
            self.console.print(Rule(Text("What Changed", style="bold white"), style=SECONDARY))
            self.console.print()
            self.console.print(
                Panel(
                    result.pr_description,
                    border_style=BORDER_COLOR,
                    padding=(1, 2),
                )
            )

        if not result.findings:
            self.console.print()
            self.console.print(
                Panel(
                    Align.center(Text("No issues found! Your code looks great.", style="bold #22C55E")),
                    border_style="#22C55E",
                    padding=(1, 2),
                )
            )
            self.console.print()
            _detach_console(self.console)
            return

        # Findings count
        critical = sum(1 for f in result.findings if f.severity == "critical")
        warnings = sum(1 for f in result.findings if f.severity == "warning")
        suggestions = sum(1 for f in result.findings if f.severity == "suggestion")

        self.console.print()
        count_text = Text("  Found: ", style="bold white")
        parts = []
        if critical:
            parts.append(Text(f"{critical} critical", style=f"bold {SEVERITY_COLORS['critical']}"))
        if warnings:
            parts.append(Text(f"{warnings} warning(s)", style=f"bold {SEVERITY_COLORS['warning']}"))
        if suggestions:
            parts.append(Text(f"{suggestions} suggestion(s)", style=f"bold {SEVERITY_COLORS['suggestion']}"))

        for i, part in enumerate(parts):
            count_text.append_text(part)
            if i < len(parts) - 1:
                count_text.append(" | ", style=DIM_TEXT)

        self.console.print(count_text)
        self.console.print()

        # Individual findings
        for i, finding in enumerate(result.findings, 1):
            sev_color = SEVERITY_COLORS.get(finding.severity, "#FFFFFF")
            cat_label = CATEGORY_LABELS.get(finding.category, finding.category.title())

            # Location
            location = finding.file_path
            if finding.line_start:
                location += f":{finding.line_start}"
                if finding.line_end and finding.line_end != finding.line_start:
                    location += f"-{finding.line_end}"

            # Finding content
            content = Text()
            content.append(f"{location}\n", style=DIM_TEXT)
            content.append(f"\n{finding.description}", style="white")
            if finding.suggested_fix:
                content.append(f"\n\n", style="white")
                content.append("Fix: ", style=f"bold #22C55E")
                content.append(finding.suggested_fix, style="#22C55E")

            # Title with severity badge
            title = Text()
            title.append(f" {finding.severity.upper()} ", style=f"bold white on {sev_color}")
            title.append(f" {cat_label} ", style=f"bold {DIM_TEXT}")
            title.append(f"\u2014 {finding.title}", style="bold white")

            self.console.print(
                Panel(
                    content,
                    title=title,
                    title_align="left",
                    border_style=sev_color,
                    padding=(1, 2),
                )
            )

        # Summary
        if result.summary:
            self.console.print()
            summary_header = Text()
            summary_header.append("\u25C9 ", style=f"bold {PRIMARY}")
            summary_header.append("Summary", style="bold white")
            self.console.print(Rule(summary_header, style=BORDER_COLOR))
            self.console.print(f"  {result.summary}", style="white")
            self.console.print()

        # Status bar
        self._print_status_bar("Review complete")
        self.console.print()

        _detach_console(self.console)

    def show_error(self, message: str):
        """Display an error message."""
        self.console.print()
        err = Text()
        err.append(" ERROR ", style="bold white on #EF4444")
        err.append(f" {message}", style="bold #EF4444")
        self.console.print(err)
        self.console.print()
        _detach_console(self.console)

    def show_no_changes(self):
        """Display a 'no changes' message."""
        self.console.print()
        msg = Text()
        msg.append("  \u25C9 ", style=f"bold {PRIMARY}")
        msg.append("No changes found to review.", style=f"bold {DIM_TEXT}")
        self.console.print(msg)
        self.console.print()
        _detach_console(self.console)

    def cleanup(self):
        """Clean up console resources."""
        _detach_console(self.console)
