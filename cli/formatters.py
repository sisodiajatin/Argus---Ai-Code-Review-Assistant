"""Output formatters for CLI review results.

Supports Rich (colored terminal), JSON, and plain text output.
"""

import io
import json
import re
import sys

from app.models.schemas import AIFinding
from app.services.review_pipeline import ReviewResult


def _sanitize_for_console(text: str) -> str:
    """Remove characters that can't be rendered on Windows legacy consoles."""
    if sys.platform == "win32":
        # Remove emoji and other non-BMP characters, and problematic BMP symbols
        return text.encode("cp1252", errors="replace").decode("cp1252")
    return text


# Severity → (Rich style, plain prefix, emoji)
SEVERITY_STYLES = {
    "critical": ("bold red", "CRITICAL", "[!!]"),
    "warning": ("yellow", "WARNING", "[!]"),
    "suggestion": ("cyan", "SUGGESTION", "[~]"),
}

# Category → emoji for rich output
CATEGORY_ICONS = {
    "bug": "Bug",
    "security": "Security",
    "performance": "Performance",
    "style": "Style",
    "architecture": "Architecture",
}


class RichFormatter:
    """Colored terminal output using the Rich library."""

    def print_review(self, result: ReviewResult, verbose: bool = False):
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        from rich.rule import Rule

        # Force UTF-8 output on Windows to avoid cp1252 encoding issues
        _wrapper = None
        if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
            _wrapper = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            console = Console(file=_wrapper)
        else:
            console = Console()

        # Header
        console.print()
        console.print(Rule("[bold #00D4FF]Argus Code Review[/bold #00D4FF]"))
        console.print()

        # Stats bar
        stats = Table(show_header=False, box=None, padding=(0, 2))
        stats.add_column(style="bold")
        stats.add_column()
        stats.add_row("Files reviewed", str(result.files_reviewed))
        stats.add_row("Chunks processed", str(result.chunks_processed))
        stats.add_row("Model", result.model_used)
        stats.add_row("Tokens used", f"{result.tokens_used:,}")
        stats.add_row("Time", f"{result.processing_time_ms:.0f}ms")
        console.print(Panel(stats, title="Review Stats", border_style="dim"))

        # PR Description (what the changes do)
        if result.pr_description:
            console.print()
            console.print(Rule("[bold]What Changed[/bold]"))
            console.print(result.pr_description)
            console.print()

        if not result.findings:
            console.print()
            console.print("[bold green]No issues found! Your code looks good.[/bold green]")
            console.print()
            # Detach wrapper to avoid closing sys.stdout.buffer
            if _wrapper is not None:
                _wrapper.detach()
            return

        # Findings summary counts
        critical = sum(1 for f in result.findings if f.severity == "critical")
        warnings = sum(1 for f in result.findings if f.severity == "warning")
        suggestions = sum(1 for f in result.findings if f.severity == "suggestion")

        console.print()
        summary_parts = []
        if critical:
            summary_parts.append(f"[bold red]{critical} critical[/bold red]")
        if warnings:
            summary_parts.append(f"[yellow]{warnings} warning(s)[/yellow]")
        if suggestions:
            summary_parts.append(f"[cyan]{suggestions} suggestion(s)[/cyan]")
        console.print(f"Found {' | '.join(summary_parts)}")
        console.print()

        # Individual findings
        for i, finding in enumerate(result.findings, 1):
            sev_style = SEVERITY_STYLES.get(finding.severity, ("white", "INFO", "[?]"))
            cat_label = CATEGORY_ICONS.get(finding.category, finding.category)

            # Finding header
            location = f"{finding.file_path}"
            if finding.line_start:
                location += f":{finding.line_start}"
                if finding.line_end and finding.line_end != finding.line_start:
                    location += f"-{finding.line_end}"

            header = Text()
            header.append(f"[{finding.severity.upper()}]", style=sev_style[0])
            header.append(f" {cat_label} ", style="dim")
            header.append(f"— {finding.title}", style="bold")

            console.print(Panel(
                f"[dim]{location}[/dim]\n\n{finding.description}"
                + (f"\n\n[green]Suggested fix:[/green] {finding.suggested_fix}" if finding.suggested_fix else ""),
                title=header,
                border_style=sev_style[0],
            ))

        # Summary
        if result.summary:
            console.print()
            console.print(Rule("[bold]Summary[/bold]"))
            console.print(result.summary)
            console.print()

        # Detach wrapper to avoid closing sys.stdout.buffer
        if _wrapper is not None:
            _wrapper.detach()


class JSONFormatter:
    """JSON output for programmatic consumption."""

    def print_review(self, result: ReviewResult, verbose: bool = False):
        output = {
            "findings": [
                {
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "category": f.category,
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "suggested_fix": f.suggested_fix,
                }
                for f in result.findings
            ],
            "summary": result.summary,
            "pr_description": result.pr_description,
            "stats": {
                "files_reviewed": result.files_reviewed,
                "chunks_processed": result.chunks_processed,
                "tokens_used": result.tokens_used,
                "processing_time_ms": result.processing_time_ms,
                "model_used": result.model_used,
                "total_findings": len(result.findings),
            },
        }
        print(json.dumps(output, indent=2))


class PlainFormatter:
    """Plain text output without colors."""

    def print_review(self, result: ReviewResult, verbose: bool = False):
        print("=" * 60)
        print("ARGUS CODE REVIEW")
        print("=" * 60)
        print(f"Files: {result.files_reviewed} | Chunks: {result.chunks_processed} | "
              f"Model: {result.model_used} | Tokens: {result.tokens_used}")
        print()

        if result.pr_description:
            print("WHAT CHANGED")
            print("-" * 60)
            desc = result.pr_description.encode("ascii", errors="ignore").decode("ascii")
            print(desc)
            print()

        if not result.findings:
            print("No issues found! Your code looks good.")
            return

        critical = sum(1 for f in result.findings if f.severity == "critical")
        warnings = sum(1 for f in result.findings if f.severity == "warning")
        suggestions = sum(1 for f in result.findings if f.severity == "suggestion")
        print(f"Found: {critical} critical | {warnings} warnings | {suggestions} suggestions")
        print("-" * 60)

        for i, finding in enumerate(result.findings, 1):
            prefix = SEVERITY_STYLES.get(finding.severity, ("", "INFO", "[?]"))[2]
            location = finding.file_path
            if finding.line_start:
                location += f":{finding.line_start}"

            print(f"\n{prefix} {finding.title}")
            print(f"   Location: {location}")
            print(f"   Category: {finding.category} | Severity: {finding.severity}")
            print(f"   {finding.description}")
            if finding.suggested_fix:
                print(f"   Fix: {finding.suggested_fix}")

        if result.summary:
            print("\n" + "=" * 60)
            print("SUMMARY")
            print("=" * 60)
            # Strip emojis for plain text (avoids encoding issues on Windows)
            summary = result.summary.encode("ascii", errors="ignore").decode("ascii")
            print(summary)


def get_formatter(format_name: str):
    """Get a formatter by name."""
    formatters = {
        "rich": RichFormatter,
        "json": JSONFormatter,
        "plain": PlainFormatter,
    }
    cls = formatters.get(format_name, RichFormatter)
    return cls()
