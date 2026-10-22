"""Review publisher service.

Responsible for taking AI analysis results and posting them back to GitHub
as inline review comments and a formatted summary comment.
"""

import hashlib
import logging
import re

import httpx

from app.models.schemas import AIFinding
from app.services.vcs.github_provider import GitHubProvider

logger = logging.getLogger(__name__)

ARGUS_URL = "https://github.com/sisodiajatin/Argus---Ai-Code-Review-Assistant"

# Hidden marker embedded in each inline comment so a later push can tell
# which findings are already on the PR.
FINGERPRINT_RE = re.compile(r"<!-- argus-finding:([0-9a-f]{16}) -->")

# Most findings listed in the summary when they can't be placed inline.
MAX_UNPLACED_IN_SUMMARY = 15


def finding_fingerprint(finding: AIFinding, line: int | None) -> str:
    """Stable ID for a finding at a location (file, line, title)."""
    key = f"{finding.file_path}|{line}|{finding.title.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

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
        self._commentable: dict[str, set[int]] | None = None

    def _range_commentable(self, path: str, start: int, end: int) -> bool:
        """True if every line in start..end is in the diff (needed for multi-line comments)."""
        if self._commentable is None:
            return False
        valid = self._commentable.get(path, set())
        return all(n in valid for n in range(start, end + 1))

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
        commentable_lines: dict[str, set[int]] | None = None,
    ) -> tuple[list[str], int | None]:
        """Publish a complete review: one batch of inline comments + a summary.

        Args:
            commentable_lines: file path -> new-side line numbers that are in
                the diff. GitHub rejects comments elsewhere (HTTP 422), so
                findings outside the diff go into the summary instead.

        Returns:
            (fingerprints of inline comments posted, summary comment id)

        On re-push, findings already commented at the same place are not
        re-posted, and the existing summary comment is edited.
        """
        self._commentable = commentable_lines
        placed, unplaced = self._place_findings(findings, commentable_lines)

        # Skip findings already on the PR (e.g. after a re-push or re-review)
        already_posted = await self._existing_fingerprints(repo_full_name, pr_number, installation_id)
        new_comments = [(fp, f, line) for fp, f, line in placed if fp not in already_posted]
        if len(new_comments) < len(placed):
            logger.info(f"Skipping {len(placed) - len(new_comments)} finding(s) already commented")

        posted = await self._post_inline_comments(
            repo_full_name, pr_number, commit_sha, new_comments, installation_id
        )

        # Build the formatted summary body
        summary_body = self._format_summary_comment(
            findings=findings,
            summary_text=summary_text,
            processing_time_ms=processing_time_ms,
            files_reviewed=files_reviewed,
            commit_sha=commit_sha,
            pr_description=pr_description,
            unplaced_findings=unplaced,
        )

        # Check for an existing Argus comment to edit (re-push scenario)
        existing_comment_id = await self.github.find_bot_comment(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            installation_id=installation_id,
        )

        summary_id = None
        if existing_comment_id:
            await self.github.edit_comment(
                repo_full_name=repo_full_name,
                comment_id=existing_comment_id,
                body=summary_body,
                installation_id=installation_id,
            )
            summary_id = existing_comment_id
            logger.info(f"Updated existing summary comment #{existing_comment_id}")
        else:
            summary_id = await self.github.post_issue_comment(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                body=summary_body,
                installation_id=installation_id,
            )

        logger.info(
            f"Published review on {repo_full_name}#{pr_number}: "
            f"{len(posted)} inline comments, {len(unplaced)} in summary only"
        )

        return posted, summary_id

    def _place_findings(
        self,
        findings: list[AIFinding],
        commentable_lines: dict[str, set[int]] | None,
    ) -> tuple[list[tuple[str, AIFinding, int]], list[AIFinding]]:
        """Split findings into (fingerprint, finding, line) to comment inline and the rest.

        The model's line numbers aren't trusted: a finding goes inline only if
        its line (or some line in its range) is part of the diff.
        """
        placed: list[tuple[str, AIFinding, int]] = []
        unplaced: list[AIFinding] = []
        for finding in findings:
            line = self._resolve_line(finding, commentable_lines)
            if line is None:
                unplaced.append(finding)
                continue
            placed.append((finding_fingerprint(finding, line), finding, line))
        return placed, unplaced

    @staticmethod
    def _resolve_line(finding: AIFinding, commentable_lines: dict[str, set[int]] | None) -> int | None:
        start = finding.line_start or finding.line_end
        if start is None:
            return None
        if commentable_lines is None:
            return start  # no diff info: trust the model (CLI / legacy callers)
        valid = commentable_lines.get(finding.file_path, set())
        if start in valid:
            return start
        end = finding.line_end or start
        lo, hi = min(start, end), max(start, end)
        in_range = [n for n in valid if lo <= n <= hi]
        return min(in_range) if in_range else None

    async def _existing_fingerprints(self, repo_full_name, pr_number, installation_id) -> set[str]:
        list_comments = getattr(self.github, "list_review_comments", None)
        if list_comments is None:
            return set()
        comments = await list_comments(
            repo_full_name=repo_full_name, pr_number=pr_number, installation_id=installation_id
        )
        if not isinstance(comments, list):
            return set()
        found = set()
        for comment in comments:
            match = FINGERPRINT_RE.search((comment or {}).get("body") or "")
            if match:
                found.add(match.group(1))
        return found

    async def _post_inline_comments(
        self,
        repo_full_name: str,
        pr_number: int,
        commit_sha: str,
        items: list[tuple[str, AIFinding, int]],
        installation_id: int | None,
    ) -> list[str]:
        """Post comments as a single review; fall back to one-by-one on rejection."""
        if not items:
            return []
        comments = []
        for fp, f, line in items:
            comment = {"path": f.file_path, "line": line, "side": "RIGHT",
                       "body": self._format_finding_comment(f, fp)}
            # Anchor multi-line findings to the whole range, so a ```suggestion
            # replaces exactly those lines rather than only the first one.
            end = f.line_end
            if end and end > line and self._range_commentable(f.file_path, line, end):
                comment["start_line"] = line
                comment["start_side"] = "RIGHT"
                comment["line"] = end
            comments.append(comment)
        try:
            await self.github.create_review(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                commit_sha=commit_sha,
                comments=comments,
                installation_id=installation_id,
            )
            return [fp for fp, _, _ in items]
        except httpx.HTTPStatusError as e:
            # A single bad position makes GitHub reject the whole review (422).
            # Post individually so one bad comment doesn't drop the rest.
            logger.warning(f"Batched review rejected ({e.response.status_code}); posting comments one by one")
        except Exception as e:
            logger.warning(f"Batched review failed ({e}); posting comments one by one")

        posted = []
        for (fp, finding, _), comment in zip(items, comments):
            comment_id = await self.github.post_review_comment(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                commit_sha=commit_sha,
                file_path=finding.file_path,
                line=comment["line"],
                body=comment["body"],
                side="RIGHT",
                installation_id=installation_id,
            )
            if comment_id:
                posted.append(fp)
        return posted

    def _format_summary_comment(
        self,
        findings: list[AIFinding],
        summary_text: str,
        processing_time_ms: float = 0,
        files_reviewed: int = 0,
        commit_sha: str = "",
        pr_description: str = "",
        unplaced_findings: list[AIFinding] | None = None,
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
            parts.append("**Status:** 🟡 **Minor issues found**")
        elif len(findings) > 0:
            parts.append("**Status:** 🟢 **Suggestions only — looking good!**")
        else:
            parts.append("**Status:** ✅ **No issues found — great job!**")

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

        # Findings that couldn't be attached to a diff line
        if unplaced_findings:
            parts.append("### Not shown inline")
            parts.append("")
            parts.append("_These findings point outside the changed lines:_")
            parts.append("")
            for f in unplaced_findings[:MAX_UNPLACED_IN_SUMMARY]:
                emoji = SEVERITY_EMOJI.get(f.severity, "ℹ️")
                loc = f"`{f.file_path}:{f.line_start}`" if f.line_start else f"`{f.file_path}`"
                parts.append(f"- {emoji} **{f.title}** — {loc}: {f.description}")
            if len(unplaced_findings) > MAX_UNPLACED_IN_SUMMARY:
                parts.append(f"- …and {len(unplaced_findings) - MAX_UNPLACED_IN_SUMMARY} more")
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
            f"Powered by [Argus]({ARGUS_URL})*"
        )

        return "\n".join(parts)

    def _format_finding_comment(self, finding: AIFinding, fingerprint: str = "") -> str:
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

        if fingerprint:
            parts.extend(["", f"<!-- argus-finding:{fingerprint} -->"])

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
