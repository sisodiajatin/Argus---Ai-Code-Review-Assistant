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

# Errors worth retrying: the request may succeed if sent again.
TRANSIENT_ERRORS = (
    openai.RateLimitError,
    openai.APIConnectionError,  # includes APITimeoutError
    openai.InternalServerError,
)


class ChunkAnalysisError(Exception):
    """A chunk could not be analyzed (API failure or unreadable model output)."""

    def __init__(self, chunk_id: str, cause: BaseException):
        self.chunk_id = chunk_id
        self.cause = cause
        super().__init__(f"chunk {chunk_id}: {cause.__class__.__name__}: {cause}")


class ReviewIncompleteError(Exception):
    """Some chunks failed, so the review does not cover the whole diff.

    Raised instead of returning partial results, so callers never report an
    unreviewed change as clean.
    """

    def __init__(self, failed: int, total: int, errors: list[BaseException]):
        self.failed = failed
        self.total = total
        self.errors = errors
        first = errors[0] if errors else None
        detail = f" First error: {first}" if first else ""
        super().__init__(f"{failed} of {total} chunk(s) could not be analyzed.{detail}")


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
    ) -> AIReviewResult:
        """Analyze a single review chunk and return findings.

        Args:
            chunk: The review chunk containing file changes.
            pr_title: The pull request title for context.
            pr_author: The PR author for context.
            base_branch: The target branch for context.

        Returns:
            AIReviewResult with findings and metadata.

        Raises:
            ChunkAnalysisError: if the chunk could not be analyzed. An empty
                findings list always means "reviewed, nothing found".
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

        # Call the LLM, retrying only transient failures.
        attempt = 0
        while True:
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
                break
            except TRANSIENT_ERRORS as e:
                if attempt >= self.MAX_RETRIES:
                    raise ChunkAnalysisError(chunk.chunk_id, e) from e
                delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                attempt += 1
                logger.warning(
                    f"{e.__class__.__name__} on chunk {chunk.chunk_id}, retrying in {delay}s "
                    f"(attempt {attempt}/{self.MAX_RETRIES})"
                )
                await asyncio.sleep(delay)
            except Exception as e:
                # Auth errors, bad model names, bad requests: retrying won't help.
                raise ChunkAnalysisError(chunk.chunk_id, e) from e

        # Parse the response
        response_text = response.choices[0].message.content or "{}"
        tokens_used = response.usage.total_tokens if response.usage else 0

        if not self._looks_like_findings_json(response_text):
            # A reply we can't parse means the chunk was NOT reviewed — don't
            # let it masquerade as "no findings".
            raise ChunkAnalysisError(
                chunk.chunk_id, ValueError("model response was not valid findings JSON")
            )

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

        # Collect findings from all chunks. Any failed chunk means part of the
        # diff went unreviewed, so the review as a whole is incomplete.
        failures: list[BaseException] = []
        for result in results:
            if isinstance(result, BaseException):
                logger.error(f"Chunk analysis failed: {result}")
                failures.append(result)
                continue
            all_findings.extend(result.findings)
            total_tokens += result.tokens_used

        if failures:
            raise ReviewIncompleteError(failed=len(failures), total=len(chunks), errors=failures)

        all_findings = self._dedupe_findings(all_findings)

        # Generate overall summary
        summary_text, summary_tokens = await self._generate_summary(
            all_findings=all_findings,
            pr_title=pr_title,
            pr_author=pr_author,
            chunks=chunks,
        )
        total_tokens += summary_tokens

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
    ) -> tuple[str, int]:
        """Generate a summary review comment from all findings.

        Returns (summary_text, tokens_used).
        """
        if not all_findings:
            return (
                "## ✅ AI Code Review\n\n"
                "No significant issues found in this pull request. "
                "The code changes look good!",
                0,
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
            tokens = response.usage.total_tokens if response.usage else 0
            text = response.choices[0].message.content or self._build_fallback_summary(all_findings)
            return text, tokens
        except Exception as e:
            # The findings themselves are intact; only the prose summary failed.
            logger.error(f"Failed to generate summary: {e}")
            return self._build_fallback_summary(all_findings), 0

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

    def _looks_like_findings_json(self, response_text: str) -> bool:
        """True if the reply is a JSON object (bare or fenced) we can read findings from."""
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            data = self._extract_json_from_text(response_text)
        return isinstance(data, dict)

    @staticmethod
    def _dedupe_findings(findings: list[AIFinding]) -> list[AIFinding]:
        """Drop exact repeats (same file, line and title) produced by overlapping chunks."""
        seen: set[tuple] = set()
        unique: list[AIFinding] = []
        for f in findings:
            key = (f.file_path, f.line_start, f.title.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            unique.append(f)
        return unique

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
        """Generate a plain-English summary of what the PR does (text only)."""
        text, _ = await self.generate_pr_summary_with_usage(
            chunks, pr_title, pr_author, base_branch
        )
        return text

    async def generate_pr_summary_with_usage(
        self,
        chunks: list[ReviewChunk],
        pr_title: str,
        pr_author: str,
        base_branch: str = "main",
    ) -> tuple[str, int]:
        """Generate a plain-English summary of what the PR does.

        This is NOT the review-findings summary — it describes the *purpose*
        of the changes so reviewers can understand the PR at a glance.

        Args:
            chunks: The review chunks containing file changes.
            pr_title: The pull request title.
            pr_author: The PR author.
            base_branch: Target branch.

        Returns:
            (markdown summary, tokens_used)
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
            tokens = response.usage.total_tokens if response.usage else 0
            return response.choices[0].message.content or "", tokens
        except Exception as e:
            logger.error(f"Failed to generate PR summary: {e}")
            # Fallback: simple file-list summary
            return (
                f"**Changes in {len(file_paths)} file(s):**\n"
                + "\n".join(f"- `{p}`" for p in file_paths[:15])
            ), 0
