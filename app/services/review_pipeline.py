"""Reusable review pipeline service.

Orchestrates the diff parsing → smart chunking → AI analysis pipeline.
Used by both the webhook handler (for GitHub PRs) and the CLI (for local reviews).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.config import BaseAppSettings, get_base_settings
from app.models.schemas import AIFinding, FileChange
from app.services.vcs.base import PRFile
from app.services.diff_parser import DiffParser
from app.services.chunker import SmartChunker
from app.services.analyzer import AIAnalyzer

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
    ) -> ReviewResult:
        """Execute the full review pipeline and return results.

        Args:
            pr_files: List of changed files (from GitHub API or local git).
            title: PR title or local review description.
            author: Author of the changes.
            base_branch: Target branch for context.
            ignored_paths: Glob patterns for files to skip.

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

        # Step 3: Run review analysis and PR summary generation concurrently
        review_task = self.analyzer.analyze_pr(
            chunks=chunks,
            pr_title=title,
            pr_author=author,
            base_branch=base_branch,
        )
        summary_task = self.analyzer.generate_pr_summary(
            chunks=chunks,
            pr_title=title,
            pr_author=author,
            base_branch=base_branch,
        )

        (all_findings, summary_text, total_tokens, analysis_time_ms), pr_description = (
            await asyncio.gather(review_task, summary_task)
        )

        # Post-analysis filtering: apply focus categories and severity threshold
        filtered_findings = self._filter_findings(all_findings)
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
