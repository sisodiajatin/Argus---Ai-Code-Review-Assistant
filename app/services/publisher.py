"""Review publisher service.

Responsible for taking AI analysis results and posting them back to GitHub
as inline review comments and a formatted summary comment.
"""

import logging

from app.models.schemas import AIFinding
from app.services.vcs.github_provider import GitHubProvider

logger = logging.getLogger(__name__)

# Severity emoji mapping for inline comments
SEVERITY_EMOJI = {
    "critical": "🔴",
    "warning": "🟡",
    "suggestion": "🟢",
}

# Category labels for inline comments
CATEGORY_LABELS = {
    "bug": "🐛 Bug",
    "security": "🔒 Security",
    "performance": "⚡ Performance",
    "style": "✨ Style",
    "architecture": "🏗️ Architecture",
}


class ReviewPublisher:
    """Publishes AI review findings as GitHub PR comments."""

    def __init__(self, github_provider: GitHubProvider):
        self.github = github_provider

    async def publish_review(
        self,
        repo_full_name: str,
        pr_number: int,
        commit_sha: str,
        findings: list[AIFinding],
        summary_text: str,
        processing_time_ms: float = 0,
        files_reviewed: int = 0,
        installation_id: int | None = None,
        pr_description: str = "",
    ) -> tuple[list[int], int | None]:
        """Publish a complete review: inline comments + formatted summary.

        On re-push, edits the existing Argus summary comment instead of
        creating a new one to keep the PR clean.
        """
        comment_ids = []

        # Post inline comments for each finding
        for finding in findings:
            comment_id = await self._post_inline_comment(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                commit_sha=commit_sha,
                finding=finding,
                installation_id=installation_id,
            )
            if comment_id:
                comment_ids.append(comment_id)

        # Build the formatted summary body
        summary_body = self._format_summary_comment(
            findings=findings,
            summary_text=summary_text,
            processing_time_ms=processing_time_ms,
            files_reviewed=files_reviewed,
            commit_sha=commit_sha,
            pr_description=pr_description,
        )

        # Check for an existing Argus comment to edit (re-push scenario)
        existing_comment_id = await self.github.find_bot_comment(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            installation_id=installation_id,
        )

        summary_id = None
        if existing_comment_id:
            # Edit the existing comment
            await self.github.edit_comment(
                repo_full_name=repo_full_name,
                comment_id=existing_comment_id,
                body=summary_body,
                installation_id=installation_id,
            )
            summary_id = existing_comment_id
            logger.info(f"Updated existing summary comment #{existing_comment_id}")
        else:
            # Post a new issue comment
            summary_id = await self.github.post_issue_comment(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                body=summary_body,
                installation_id=installation_id,
            )

        logger.info(
            f"Published review on {repo_full_name}#{pr_number}: "
            f"{len(comment_ids)} inline comments"
        )

        return comment_ids, summary_id

    def _format_summary_comment(
        self,
        findings: list[AIFinding],
        summary_text: str,
        processing_time_ms: float = 0,
        files_reviewed: int = 0,
        commit_sha: str = "",
        pr_description: str = "",
    ) -> str:
        """Build a formatted markdown summary comment for the PR."""
        critical = sum(1 for f in findings if f.severity == "critical")
        warnings = sum(1 for f in findings if f.severity == "warning")
        suggestions = sum(1 for f in findings if f.severity == "suggestion")

        # Header with hidden marker for finding existing comments
        parts = ["<!-- argus-review-summary -->"]
        parts.append("## 👁️ Argus Code Review")
        parts.append("")

        # PR auto-summary (what the PR does)
        if pr_description:
            parts.append("### PR Summary")
            parts.append("")
            parts.append(pr_description)
            parts.append("")

        # Status line
        if critical > 0:
            parts.append(f"**Status:** 🔴 **{critical} critical issue{'s' if critical != 1 else ''} found**")
        elif warnings > 0:
            parts.append(f"**Status:** 🟡 **Minor issues found**")
        elif len(findings) > 0:
            parts.append(f"**Status:** 🟢 **Suggestions only — looking good!**")
        else:
            parts.append(f"**Status:** ✅ **No issues found — great job!**")

        parts.append("")

        # Severity breakdown table
        if findings:
            parts.append("| Severity | Count |")
            parts.append("|----------|-------|")
            if critical:
                parts.append(f"| 🔴 Critical | {critical} |")
            if warnings:
                parts.append(f"| 🟡 Warning | {warnings} |")
            if suggestions:
                parts.append(f"| 🟢 Suggestion | {suggestions} |")
            parts.append("")

        # Top findings (up to 5)
        top_findings = [f for f in findings if f.severity in ("critical", "warning")][:5]
        if top_findings:
            parts.append("### Top Findings")
            parts.append("")
            for f in top_findings:
                emoji = SEVERITY_EMOJI.get(f.severity, "ℹ️")
                cat = CATEGORY_LABELS.get(f.category, f.category)
                file_ref = f"`{f.file_path}"
                if f.line_start:
                    file_ref += f":{f.line_start}"
                file_ref += "`"
                parts.append(f"- {emoji} **{f.title}** ({cat}) — {file_ref}")
            parts.append("")

        # AI summary
        if summary_text:
            parts.append("### Summary")
            parts.append("")
            parts.append(summary_text)
            parts.append("")

        # Footer
        time_str = f"{processing_time_ms / 1000:.1f}s" if processing_time_ms else "—"
        sha_short = commit_sha[:7] if commit_sha else "—"
        parts.append("---")
        parts.append(
            f"*Reviewed commit `{sha_short}` • "
            f"{files_reviewed} file{'s' if files_reviewed != 1 else ''} • "
            f"{len(findings)} finding{'s' if len(findings) != 1 else ''} • "
            f"{time_str} • "
            f"Powered by [Argus](https://github.com/sisodiajatin/argus)*"
        )

        return "\n".join(parts)

    async def _post_inline_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        commit_sha: str,
        finding: AIFinding,
        installation_id: int | None = None,
    ) -> int | None:
        """Post a single inline review comment for a finding."""
        body = self._format_finding_comment(finding)

        line = finding.line_start or finding.line_end
        if line is None:
            logger.warning(
                f"Finding has no line number, skipping inline comment: {finding.title}"
            )
            return None

        return await self.github.post_review_comment(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            commit_sha=commit_sha,
            file_path=finding.file_path,
            line=line,
            body=body,
            side="RIGHT",
            installation_id=installation_id,
        )

    def _format_finding_comment(self, finding: AIFinding) -> str:
        """Format a finding into a rich inline comment body.

        Uses GitHub's suggestion syntax when the suggested_fix looks like
        replacement code, so reviewers get a 1-click "Apply suggestion" button.
        """
        severity_emoji = SEVERITY_EMOJI.get(finding.severity, "ℹ️")
        category_label = CATEGORY_LABELS.get(finding.category, finding.category)

        parts = [
            f"### {severity_emoji} {finding.title}",
            f"**{category_label}** | Severity: **{finding.severity}**",
            "",
            finding.description,
        ]

        if finding.suggested_fix:
            fix = finding.suggested_fix.strip()
            if self._looks_like_code(fix):
                parts.extend(["", "```suggestion", fix, "```"])
            else:
                parts.extend(["", "**Suggested fix:**", fix])

        return "\n".join(parts)

    @staticmethod
    def _looks_like_code(text: str) -> bool:
        """Heuristic: return True if the text looks like replacement code."""
        lines = text.strip().splitlines()
        if not lines:
            return False
        code_indicators = (
            "def ", "class ", "import ", "from ", "return ", "if ", "for ",
            "const ", "let ", "var ", "function ", "export ", "async ",
            "func ", "fn ", "pub ", "impl ", "struct ",
            "=", "(", "{", "->", "=>", ";",
        )
        code_line_count = sum(
            1 for line in lines
            if any(ind in line for ind in code_indicators)
        )
        return code_line_count / len(lines) >= 0.4

    @staticmethod
    def _determine_review_event(findings: list[AIFinding]) -> str:
        """Determine the GitHub review event based on findings severity."""
        has_critical = any(f.severity == "critical" for f in findings)
        if has_critical:
            return "COMMENT"
        return "COMMENT"
