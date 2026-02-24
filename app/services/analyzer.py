"""AI-powered code analysis service.

Uses OpenAI's API to analyze code changes and generate review findings.
Handles prompt construction, API communication, response parsing, and
error recovery.
"""

import asyncio
import json
import logging
import time
from typing import Any

import openai

from app.config import BaseAppSettings, get_base_settings
from app.models.schemas import AIFinding, AIReviewResult, FileChange, ReviewChunk
from app.prompts.system import SYSTEM_PROMPT
from app.prompts.review import build_review_prompt, build_summary_prompt, build_pr_summary_prompt
from app.prompts.languages import get_language_hints
from app.services.diff_parser import DiffParser

logger = logging.getLogger(__name__)


class AIAnalyzer:
    """Analyzes code diffs using OpenAI's LLM and returns structured findings."""

    def __init__(self, settings: BaseAppSettings | None = None):
        self.settings = settings or get_base_settings()
        self.client = openai.AsyncOpenAI(
            api_key=self.settings.ai_api_key,
            base_url=self.settings.ai_base_url,
        )
        self.diff_parser = DiffParser()

    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 5  # seconds

    async def analyze_chunk(
        self,
        chunk: ReviewChunk,
        pr_title: str,
        pr_author: str,
        base_branch: str = "main",
        _retry_count: int = 0,
    ) -> AIReviewResult:
        """Analyze a single review chunk and return findings.

        Args:
            chunk: The review chunk containing file changes.
            pr_title: The pull request title for context.
            pr_author: The PR author for context.
            base_branch: The target branch for context.
            _retry_count: Internal retry counter (do not set manually).

        Returns:
            AIReviewResult with findings and metadata.
        """
        start_time = time.time()

        # Format the diff content for the LLM
        diff_content = self._format_chunk_for_llm(chunk)

        # Build the review prompt
        prompt = build_review_prompt(
            pr_title=pr_title,
            pr_author=pr_author,
            diff_content=diff_content,
            base_branch=base_branch,
        )

        # Build system prompt with language-specific hints
        extensions = {
            "." + f.file_path.rsplit(".", 1)[-1]
            for f in chunk.files
            if "." in f.file_path
        }
        lang_hints = get_language_hints(extensions)
        system_prompt = SYSTEM_PROMPT
        if lang_hints:
            system_prompt += "\n\n" + lang_hints

        # Call the LLM
        try:
            response = await self.client.chat.completions.create(
                model=self.settings.ai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=4096,
                response_format={"type": "json_object"},
            )

            # Parse the response
            response_text = response.choices[0].message.content or "{}"
            tokens_used = response.usage.total_tokens if response.usage else 0

            findings = self._parse_findings(response_text)
            summary = self._extract_summary(response_text)

            elapsed_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Analyzed chunk {chunk.chunk_id}: {len(findings)} findings, "
                f"{tokens_used} tokens, {elapsed_ms:.0f}ms"
            )

            return AIReviewResult(
                findings=findings,
                summary=summary,
                tokens_used=tokens_used,
            )

        except openai.RateLimitError:
            if _retry_count >= self.MAX_RETRIES:
                logger.error(
                    f"Rate limit exceeded after {self.MAX_RETRIES} retries "
                    f"for chunk {chunk.chunk_id}"
                )
                return AIReviewResult(
                    findings=[],
                    summary="Rate limit exceeded — could not analyze this chunk.",
                    tokens_used=0,
                )
            delay = self.RETRY_BASE_DELAY * (2 ** _retry_count)
            logger.warning(
                f"Rate limit hit, retrying in {delay}s "
                f"(attempt {_retry_count + 1}/{self.MAX_RETRIES})"
            )
            await asyncio.sleep(delay)
            return await self.analyze_chunk(
                chunk, pr_title, pr_author, base_branch,
                _retry_count=_retry_count + 1,
            )

        except openai.APIError as e:
            logger.error(f"OpenAI API error analyzing chunk {chunk.chunk_id}: {e}")
            return AIReviewResult(
                findings=[],
                summary=f"Error analyzing this chunk: {str(e)}",
                tokens_used=0,
            )

        except Exception as e:
            logger.error(f"Unexpected error analyzing chunk {chunk.chunk_id}: {e}")
            return AIReviewResult(
                findings=[],
                summary=f"Unexpected error: {str(e)}",
                tokens_used=0,
            )

    async def analyze_pr(
        self,
        chunks: list[ReviewChunk],
        pr_title: str,
        pr_author: str,
        base_branch: str = "main",
    ) -> tuple[list[AIFinding], str, int, float]:
        """Analyze all chunks of a PR and compile results.

        Args:
            chunks: List of review chunks to analyze.
            pr_title: The pull request title.
            pr_author: The PR author.
            base_branch: The target branch.

        Returns:
            Tuple of (all_findings, summary_text, total_tokens, processing_time_ms)
        """
        start_time = time.time()
        all_findings: list[AIFinding] = []
        total_tokens = 0

        # Analyze chunks concurrently (with some concurrency limit)
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent API calls

        async def analyze_with_limit(chunk: ReviewChunk) -> AIReviewResult:
            async with semaphore:
                return await self.analyze_chunk(chunk, pr_title, pr_author, base_branch)

        results = await asyncio.gather(
            *[analyze_with_limit(chunk) for chunk in chunks],
            return_exceptions=True,
        )

        # Collect findings from all chunks
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Chunk analysis failed: {result}")
                continue
            all_findings.extend(result.findings)
            total_tokens += result.tokens_used

        # Generate overall summary
        summary_text = await self._generate_summary(
            all_findings=all_findings,
            pr_title=pr_title,
            pr_author=pr_author,
            chunks=chunks,
        )

        processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"PR analysis complete: {len(all_findings)} findings from {len(chunks)} chunks, "
            f"{total_tokens} tokens, {processing_time_ms:.0f}ms"
        )

        return all_findings, summary_text, total_tokens, processing_time_ms

    async def _generate_summary(
        self,
        all_findings: list[AIFinding],
        pr_title: str,
        pr_author: str,
        chunks: list[ReviewChunk],
    ) -> str:
        """Generate a summary review comment from all findings."""
        if not all_findings:
            return (
                "## ✅ AI Code Review\n\n"
                "No significant issues found in this pull request. "
                "The code changes look good!"
            )

        # Format findings for the summary prompt
        findings_text = ""
        for i, finding in enumerate(all_findings, 1):
            findings_text += (
                f"\n### Finding {i}\n"
                f"- **File**: {finding.file_path}:{finding.line_start or '?'}\n"
                f"- **Category**: {finding.category}\n"
                f"- **Severity**: {finding.severity}\n"
                f"- **Title**: {finding.title}\n"
                f"- **Description**: {finding.description}\n"
            )

        # Calculate stats
        total_additions = sum(
            f.additions for chunk in chunks for f in chunk.files
        )
        total_deletions = sum(
            f.deletions for chunk in chunks for f in chunk.files
        )
        total_files = sum(len(chunk.files) for chunk in chunks)

        summary_prompt = build_summary_prompt(
            pr_title=pr_title,
            pr_author=pr_author,
            files_changed=total_files,
            additions=total_additions,
            deletions=total_deletions,
            findings_text=findings_text,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.settings.ai_model,
                messages=[
                    {"role": "system", "content": "You are an expert code reviewer generating a summary of review findings."},
                    {"role": "user", "content": summary_prompt},
                ],
                temperature=0.3,
                max_tokens=2048,
            )
            return response.choices[0].message.content or "Summary generation failed."
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return self._build_fallback_summary(all_findings)

    def _format_chunk_for_llm(self, chunk: ReviewChunk) -> str:
        """Format a review chunk into a string suitable for LLM input."""
        parts = []
        for file in chunk.files:
            formatted = self.diff_parser.format_diff_for_llm(file)
            parts.append(formatted)
        return "\n---\n".join(parts)

    def _parse_findings(self, response_text: str) -> list[AIFinding]:
        """Parse LLM response text into structured findings."""
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            data = self._extract_json_from_text(response_text)
            if data is None:
                logger.warning("Failed to parse LLM response as JSON")
                return []

        raw_findings = data.get("findings", [])
        findings = []

        for raw in raw_findings:
            try:
                finding = AIFinding(
                    file_path=raw.get("file_path", "unknown"),
                    line_start=raw.get("line_start"),
                    line_end=raw.get("line_end"),
                    category=self._validate_category(raw.get("category", "style")),
                    severity=self._validate_severity(raw.get("severity", "suggestion")),
                    title=raw.get("title", "Untitled finding"),
                    description=raw.get("description", "No description provided."),
                    suggested_fix=raw.get("suggested_fix"),
                )
                findings.append(finding)
            except Exception as e:
                logger.warning(f"Failed to parse individual finding: {e}")
                continue

        return findings

    def _extract_summary(self, response_text: str) -> str:
        """Extract the summary field from the LLM response."""
        try:
            data = json.loads(response_text)
            return data.get("summary", "")
        except json.JSONDecodeError:
            return ""

    @staticmethod
    def _extract_json_from_text(text: str) -> dict[str, Any] | None:
        """Try to extract JSON from text that may contain markdown code blocks."""
        import re
        # Try to find JSON in code blocks
        patterns = [
            r"```json\s*(.*?)\s*```",
            r"```\s*(.*?)\s*```",
            r"\{.*\}",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1) if match.lastindex else match.group())
                except (json.JSONDecodeError, IndexError):
                    continue
        return None

    @staticmethod
    def _validate_category(category: str) -> str:
        """Validate and normalize a finding category."""
        valid = {"bug", "security", "performance", "style", "architecture"}
        cat = category.lower().strip()
        return cat if cat in valid else "style"

    @staticmethod
    def _validate_severity(severity: str) -> str:
        """Validate and normalize a finding severity."""
        valid = {"critical", "warning", "suggestion"}
        sev = severity.lower().strip()
        return sev if sev in valid else "suggestion"

    @staticmethod
    def _build_fallback_summary(findings: list[AIFinding]) -> str:
        """Build a simple summary when LLM summary generation fails."""
        critical = sum(1 for f in findings if f.severity == "critical")
        warnings = sum(1 for f in findings if f.severity == "warning")
        suggestions = sum(1 for f in findings if f.severity == "suggestion")

        summary = "## 🤖 AI Code Review Summary\n\n"
        summary += f"Found **{len(findings)}** issue(s):\n"
        if critical:
            summary += f"- 🔴 **{critical}** critical\n"
        if warnings:
            summary += f"- 🟡 **{warnings}** warning(s)\n"
        if suggestions:
            summary += f"- 🟢 **{suggestions}** suggestion(s)\n"

        if critical:
            summary += "\n### Critical Issues\n"
            for f in findings:
                if f.severity == "critical":
                    summary += f"- **{f.title}** in `{f.file_path}`\n"

        return summary

    async def generate_pr_summary(
        self,
        chunks: list[ReviewChunk],
        pr_title: str,
        pr_author: str,
        base_branch: str = "main",
    ) -> str:
        """Generate a plain-English summary of what the PR does.

        This is NOT the review-findings summary — it describes the *purpose*
        of the changes so reviewers can understand the PR at a glance.

        Args:
            chunks: The review chunks containing file changes.
            pr_title: The pull request title.
            pr_author: The PR author.
            base_branch: Target branch.

        Returns:
            Markdown-formatted PR summary string.
        """
        # Collect file list and abbreviated diffs
        file_paths: list[str] = []
        diff_parts: list[str] = []
        total_additions = 0
        total_deletions = 0
        max_diff_chars = 6000  # Keep prompt size reasonable

        for chunk in chunks:
            for f in chunk.files:
                file_paths.append(f.file_path)
                total_additions += f.additions
                total_deletions += f.deletions

        file_list = "\n".join(f"- `{p}`" for p in file_paths)

        # Build abbreviated diff (first N chars across chunks)
        chars_remaining = max_diff_chars
        for chunk in chunks:
            part = self._format_chunk_for_llm(chunk)
            if len(part) > chars_remaining:
                diff_parts.append(part[:chars_remaining] + "\n... (truncated)")
                break
            diff_parts.append(part)
            chars_remaining -= len(part)

        diff_content = "\n---\n".join(diff_parts)

        prompt = build_pr_summary_prompt(
            pr_title=pr_title,
            pr_author=pr_author,
            base_branch=base_branch,
            files_changed=len(file_paths),
            additions=total_additions,
            deletions=total_deletions,
            file_list=file_list,
            diff_content=diff_content,
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.settings.ai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a senior developer writing a concise PR "
                            "summary for your team. Be clear and factual."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Failed to generate PR summary: {e}")
            # Fallback: simple file-list summary
            return (
                f"**Changes in {len(file_paths)} file(s):**\n"
                + "\n".join(f"- `{p}`" for p in file_paths[:15])
            )
