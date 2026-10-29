"""Reusable review pipeline service.

Orchestrates the diff parsing → smart chunking → AI analysis pipeline.
Used by both the webhook handler (for GitHub PRs) and the CLI (for local reviews).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.config import BaseAppSettings, get_base_settings
from app.models.schemas import AIFinding
from app.services.vcs.base import PRFile
from app.services.diff_parser import DiffParser
from app.services.chunker import SmartChunker
from app.services.analyzer import AIAnalyzer
from app.services.feedback import FeedbackMemory, apply_feedback, build_feedback_hint

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"critical": 2, "warning": 1, "suggestion": 0}


@dataclass
class ReviewResult:
    """Complete result from a review pipeline run."""
    findings: list[AIFinding] = field(default_factory=list)
    summary: str = ""
    pr_description: str = ""  # Plain-English "what this PR does" summary
    tokens_used: int = 0
    processing_time_ms: float = 0.0
    chunks_processed: int = 0
    files_reviewed: int = 0
    model_used: str = ""
    # Findings hidden because similar ones were marked "not helpful" in this repo
    suppressed_findings: list[AIFinding] = field(default_factory=list)


class ReviewPipeline:
    """Orchestrates the diff → chunk → analyze pipeline.

    Reusable by both the webhook handler and the CLI.
    """

    def __init__(self, settings: BaseAppSettings | None = None):
        self.settings = settings or get_base_settings()
        self.diff_parser = DiffParser()
        self.chunker = SmartChunker(settings=self.settings)
        self.analyzer = AIAnalyzer(settings=self.settings)

    async def run(
        self,
        pr_files: list[PRFile],
        title: str,
        author: str,
        base_branch: str = "main",
        ignored_paths: list[str] | None = None,
        feedback: FeedbackMemory | None = None,
        description_files: list[PRFile] | None = None,
    ) -> ReviewResult:
        """Execute the full review pipeline and return results.

        Args:
            pr_files: List of changed files (from GitHub API or local git).
            title: PR title or local review description.
            author: Author of the changes.
            base_branch: Target branch for context.
            ignored_paths: Glob patterns for files to skip.
            feedback: Past reviewer feedback for this repository, if any.
            description_files: Files to describe in the PR summary when they
                differ from pr_files (incremental reviews describe the whole PR).

        Returns:
            ReviewResult with findings, summary, and metadata.
        """
        start_time = time.time()

        # Step 1: Parse diffs into structured file changes
        file_changes = self.diff_parser.parse_pr_files(pr_files)
        logger.info(f"Parsed {len(file_changes)} file changes")

        # Step 2: Create smart chunks
        chunks = self.chunker.create_chunks(file_changes, ignored_paths or [])

        if not chunks:
            logger.info("No reviewable chunks found")
            return ReviewResult(
                summary="No reviewable changes found.",
                files_reviewed=len(file_changes),
                model_used=self.settings.ai_model,
            )

        logger.info(f"Created {len(chunks)} chunks for review")

        # Findings this repo's reviewers already rejected are removed before the
        # summary is written, and collected so they can be shown, not lost.
        suppressed: list[AIFinding] = []

        def _suppress(findings: list[AIFinding]) -> list[AIFinding]:
            kept, hidden = apply_feedback(findings, feedback)
            suppressed.extend(hidden)
            return kept

        # Step 3: Run review analysis and PR summary generation concurrently
        review_task = self.analyzer.analyze_pr(
            chunks=chunks,
            pr_title=title,
            pr_author=author,
            base_branch=base_branch,
            feedback_hint=build_feedback_hint(feedback),
            finding_filter=_suppress,
        )
        description_chunks = chunks
        if description_files is not None:
            description_chunks = self.chunker.create_chunks(
                self.diff_parser.parse_pr_files(description_files), ignored_paths or []
            ) or chunks
        summary_task = self.analyzer.generate_pr_summary_with_usage(
            chunks=description_chunks,
            pr_title=title,
            pr_author=author,
            base_branch=base_branch,
        )

        # If any chunk fails, analyze_pr raises ReviewIncompleteError and the
        # whole run fails: a partially reviewed diff must not look clean.
        (all_findings, summary_text, total_tokens, _), (pr_description, desc_tokens) = (
            await asyncio.gather(review_task, summary_task)
        )
        total_tokens += desc_tokens

        # Post-analysis filtering: apply focus categories and severity threshold
        filtered_findings = self._filter_findings(all_findings)
        if suppressed:
            logger.info(f"Suppressed {len(suppressed)} finding(s) based on reviewer feedback")
        if len(filtered_findings) < len(all_findings):
            logger.info(
                f"Filtered {len(all_findings)} → {len(filtered_findings)} findings "
                f"(focus={self.settings.review_focus or 'all'}, "
                f"threshold={self.settings.severity_threshold})"
            )

        processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Review complete: {len(filtered_findings)} findings, "
            f"{total_tokens} tokens, {processing_time_ms:.0f}ms"
        )

        return ReviewResult(
            findings=filtered_findings,
            summary=summary_text,
            pr_description=pr_description,
            tokens_used=total_tokens,
            processing_time_ms=processing_time_ms,
            chunks_processed=len(chunks),
            files_reviewed=len(file_changes),
            model_used=self.settings.ai_model,
            suppressed_findings=suppressed,
        )

    def _filter_findings(self, findings: list[AIFinding]) -> list[AIFinding]:
        """Apply focus and severity_threshold filters to findings."""
        focus = self.settings.review_focus
        threshold = self.settings.severity_threshold
        min_rank = SEVERITY_RANK.get(threshold, 0)

        result = []
        for f in findings:
            if focus and f.category not in focus:
                continue
            if SEVERITY_RANK.get(f.severity, 0) < min_rank:
                continue
            result.append(f)
        return result
