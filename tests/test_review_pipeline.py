"""Tests for the ReviewPipeline service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.review_pipeline import ReviewPipeline, ReviewResult
from app.services.vcs.base import PRFile
from app.models.schemas import AIFinding


@pytest.fixture
def sample_pr_files():
    """Create sample PRFile objects for testing."""
    return [
        PRFile(
            filename="app/main.py",
            status="modified",
            additions=5,
            deletions=2,
            patch="@@ -10,6 +10,9 @@\n-old line\n+new line\n+another new line",
        ),
        PRFile(
            filename="app/utils.py",
            status="added",
            additions=20,
            deletions=0,
            patch="@@ -0,0 +1,20 @@\n+def helper():\n+    pass",
        ),
    ]


@pytest.fixture
def sample_findings():
    """Create sample AIFinding objects."""
    return [
        AIFinding(
            file_path="app/main.py",
            line_start=10,
            category="bug",
            severity="warning",
            title="Potential null reference",
            description="Variable might be None here",
            suggested_fix="Add a null check",
        ),
    ]


class TestReviewResult:
    def test_default_values(self):
        result = ReviewResult()
        assert result.findings == []
        assert result.summary == ""
        assert result.tokens_used == 0
        assert result.processing_time_ms == 0.0
        assert result.chunks_processed == 0
        assert result.files_reviewed == 0
        assert result.model_used == ""

    def test_custom_values(self, sample_findings):
        result = ReviewResult(
            findings=sample_findings,
            summary="Found issues",
            tokens_used=500,
            processing_time_ms=1234.5,
            chunks_processed=2,
            files_reviewed=3,
            model_used="test-model",
        )
        assert len(result.findings) == 1
        assert result.summary == "Found issues"
        assert result.tokens_used == 500
        assert result.model_used == "test-model"


class TestReviewPipelineInit:
    def test_creates_with_default_settings(self):
        pipeline = ReviewPipeline()
        assert pipeline.settings is not None
        assert pipeline.diff_parser is not None
        assert pipeline.chunker is not None
        assert pipeline.analyzer is not None

    def test_creates_with_custom_settings(self):
        from app.config import get_base_settings
        settings = get_base_settings()
        pipeline = ReviewPipeline(settings=settings)
        assert pipeline.settings is settings


class TestReviewPipelineRun:
    @pytest.mark.asyncio
    async def test_empty_files_returns_no_findings(self):
        pipeline = ReviewPipeline()
        result = await pipeline.run(
            pr_files=[],
            title="Test PR",
            author="testuser",
        )
        assert result.findings == []
        assert result.files_reviewed == 0

    @pytest.mark.asyncio
    async def test_no_reviewable_chunks_returns_early(self, sample_pr_files):
        pipeline = ReviewPipeline()
        # Mock chunker to return empty chunks
        pipeline.chunker.create_chunks = MagicMock(return_value=[])

        result = await pipeline.run(
            pr_files=sample_pr_files,
            title="Test PR",
            author="testuser",
        )
        assert result.summary == "No reviewable changes found."
        assert result.findings == []

    @pytest.mark.asyncio
    async def test_full_pipeline_with_findings(self, sample_pr_files, sample_findings):
        pipeline = ReviewPipeline()
        # Mock the chunker to return one chunk
        mock_chunk = MagicMock()
        pipeline.chunker.create_chunks = MagicMock(return_value=[mock_chunk])

        # Mock the analyzer to return findings
        pipeline.analyzer.analyze_pr = AsyncMock(return_value=(
            sample_findings,
            "Found 1 issue",
            100,
            500.0,
        ))

        result = await pipeline.run(
            pr_files=sample_pr_files,
            title="Test PR",
            author="testuser",
        )
        assert len(result.findings) == 1
        assert result.findings[0].title == "Potential null reference"
        assert result.summary == "Found 1 issue"
        assert result.tokens_used == 100
        assert result.chunks_processed == 1
        assert result.processing_time_ms > 0
        assert result.model_used == pipeline.settings.ai_model

    @pytest.mark.asyncio
    async def test_ignored_paths_passed_to_chunker(self, sample_pr_files):
        pipeline = ReviewPipeline()
        pipeline.chunker.create_chunks = MagicMock(return_value=[])

        await pipeline.run(
            pr_files=sample_pr_files,
            title="Test PR",
            author="testuser",
            ignored_paths=["*.lock", "vendor/*"],
        )

        # Verify ignored_paths were passed through
        call_args = pipeline.chunker.create_chunks.call_args
        assert call_args[0][1] == ["*.lock", "vendor/*"]
