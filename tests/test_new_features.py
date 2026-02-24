"""Tests for the three new features:
1. Retry with exponential backoff (analyzer)
2. GitHub suggestion syntax (publisher)
3. Review focus/severity filtering (pipeline)
4. Finding feedback (model + API)
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.schemas import AIFinding, ReviewChunk, FileChange
from app.services.analyzer import AIAnalyzer
from app.services.publisher import ReviewPublisher
from app.services.review_pipeline import ReviewPipeline, ReviewResult, SEVERITY_RANK
from cli.config_file import _parse_yaml


# ─── Feature 1: Retry with exponential backoff ───


class TestAnalyzerRetry:
    def test_max_retries_constant(self):
        assert AIAnalyzer.MAX_RETRIES == 3

    def test_retry_base_delay(self):
        assert AIAnalyzer.RETRY_BASE_DELAY == 5

    @pytest.mark.asyncio
    async def test_rate_limit_respects_max_retries(self):
        """After MAX_RETRIES rate-limit errors, should return gracefully."""
        import openai

        analyzer = AIAnalyzer.__new__(AIAnalyzer)
        analyzer.settings = MagicMock(ai_model="test-model")
        analyzer.diff_parser = MagicMock()
        analyzer.diff_parser.format_diff_for_llm = MagicMock(return_value="diff")
        analyzer.client = MagicMock()
        analyzer.client.chat = MagicMock()
        analyzer.client.chat.completions = MagicMock()
        analyzer.client.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            )
        )

        chunk = MagicMock()
        chunk.chunk_id = "test_chunk"
        chunk.files = []

        with patch("app.services.analyzer.asyncio.sleep", new_callable=AsyncMock):
            result = await analyzer.analyze_chunk(
                chunk, "Test PR", "author", "main",
                _retry_count=AIAnalyzer.MAX_RETRIES,
            )

        assert result.findings == []
        assert "Rate limit exceeded" in result.summary

    @pytest.mark.asyncio
    async def test_rate_limit_retries_with_backoff(self):
        """Should retry with exponential backoff delays."""
        import openai

        analyzer = AIAnalyzer.__new__(AIAnalyzer)
        analyzer.settings = MagicMock(ai_model="test-model")
        analyzer.diff_parser = MagicMock()
        analyzer.diff_parser.format_diff_for_llm = MagicMock(return_value="diff")
        analyzer.client = MagicMock()
        analyzer.client.chat = MagicMock()
        analyzer.client.chat.completions = MagicMock()

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise openai.RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            )

        analyzer.client.chat.completions.create = AsyncMock(side_effect=side_effect)

        chunk = MagicMock()
        chunk.chunk_id = "test_chunk"
        chunk.files = []

        with patch("app.services.analyzer.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await analyzer.analyze_chunk(chunk, "Test PR", "author")

        assert "Rate limit exceeded" in result.summary
        assert mock_sleep.call_count == AIAnalyzer.MAX_RETRIES
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays[0] == 5   # 5 * 2^0
        assert delays[1] == 10  # 5 * 2^1
        assert delays[2] == 20  # 5 * 2^2


# ─── Feature 2: GitHub suggestion syntax ───


class TestGitHubSuggestionSyntax:
    @pytest.fixture
    def publisher(self):
        mock_github = MagicMock()
        return ReviewPublisher(mock_github)

    def test_code_fix_uses_suggestion_block(self, publisher):
        finding = AIFinding(
            file_path="app.py",
            line_start=10,
            category="bug",
            severity="warning",
            title="Fix return",
            description="Should return early.",
            suggested_fix="if not valid:\n    return None",
        )
        body = publisher._format_finding_comment(finding)
        assert "```suggestion" in body
        assert "if not valid:" in body
        assert "**Suggested fix:**" not in body

    def test_text_fix_uses_plain_format(self, publisher):
        finding = AIFinding(
            file_path="app.py",
            line_start=10,
            category="style",
            severity="suggestion",
            title="Naming",
            description="Use snake_case.",
            suggested_fix="Rename the variable to follow Python naming conventions.",
        )
        body = publisher._format_finding_comment(finding)
        assert "```suggestion" not in body
        assert "**Suggested fix:**" in body

    def test_no_fix_has_no_suggestion_section(self, publisher):
        finding = AIFinding(
            file_path="app.py",
            line_start=10,
            category="bug",
            severity="critical",
            title="Bug",
            description="Something is wrong.",
        )
        body = publisher._format_finding_comment(finding)
        assert "suggestion" not in body.lower() or "Suggestion" not in body

    def test_looks_like_code_with_imports(self, publisher):
        assert publisher._looks_like_code("import os\nimport sys")
        assert publisher._looks_like_code("const x = 5;\nlet y = 10;")
        assert publisher._looks_like_code("def foo():\n    return bar")

    def test_looks_like_code_with_plain_text(self, publisher):
        assert not publisher._looks_like_code("Use environment variables instead.")
        assert not publisher._looks_like_code("Consider refactoring this module.")
        assert not publisher._looks_like_code("")


# ─── Feature 3: Review focus & severity filtering ───


class TestReviewFocusConfig:
    def test_parse_focus_from_yaml(self):
        yaml_text = """
model: gpt-4
focus:
  - security
  - bug
severity_threshold: warning
"""
        config = _parse_yaml(yaml_text)
        assert config.focus == ["security", "bug"]
        assert config.severity_threshold == "warning"

    def test_parse_empty_focus(self):
        config = _parse_yaml("model: gpt-4\n")
        assert config.focus == []
        assert config.severity_threshold is None

    def test_starter_yaml_has_focus_comments(self):
        from cli.config_file import STARTER_YAML
        assert "focus:" in STARTER_YAML
        assert "severity_threshold:" in STARTER_YAML


class TestSeverityRank:
    def test_rank_ordering(self):
        assert SEVERITY_RANK["critical"] > SEVERITY_RANK["warning"]
        assert SEVERITY_RANK["warning"] > SEVERITY_RANK["suggestion"]


class TestPipelineFiltering:
    def _make_findings(self):
        return [
            AIFinding(file_path="a.py", line_start=1, category="security", severity="critical", title="SQL injection", description="desc"),
            AIFinding(file_path="b.py", line_start=2, category="bug", severity="warning", title="Null ref", description="desc"),
            AIFinding(file_path="c.py", line_start=3, category="style", severity="suggestion", title="Naming", description="desc"),
            AIFinding(file_path="d.py", line_start=4, category="performance", severity="warning", title="N+1 query", description="desc"),
        ]

    def test_no_filter_returns_all(self):
        from app.config import BaseAppSettings
        settings = BaseAppSettings()
        pipeline = ReviewPipeline(settings=settings)
        findings = self._make_findings()
        result = pipeline._filter_findings(findings)
        assert len(result) == 4

    def test_focus_filters_categories(self):
        from app.config import BaseAppSettings
        settings = BaseAppSettings()
        settings.review_focus = ["security", "bug"]
        pipeline = ReviewPipeline(settings=settings)
        findings = self._make_findings()
        result = pipeline._filter_findings(findings)
        assert len(result) == 2
        assert all(f.category in ("security", "bug") for f in result)

    def test_severity_threshold_warning(self):
        from app.config import BaseAppSettings
        settings = BaseAppSettings()
        settings.severity_threshold = "warning"
        pipeline = ReviewPipeline(settings=settings)
        findings = self._make_findings()
        result = pipeline._filter_findings(findings)
        assert len(result) == 3
        assert all(f.severity in ("critical", "warning") for f in result)

    def test_severity_threshold_critical(self):
        from app.config import BaseAppSettings
        settings = BaseAppSettings()
        settings.severity_threshold = "critical"
        pipeline = ReviewPipeline(settings=settings)
        findings = self._make_findings()
        result = pipeline._filter_findings(findings)
        assert len(result) == 1
        assert result[0].severity == "critical"

    def test_combined_focus_and_severity(self):
        from app.config import BaseAppSettings
        settings = BaseAppSettings()
        settings.review_focus = ["security", "performance"]
        settings.severity_threshold = "warning"
        pipeline = ReviewPipeline(settings=settings)
        findings = self._make_findings()
        result = pipeline._filter_findings(findings)
        # security/critical + performance/warning
        assert len(result) == 2
        categories = {f.category for f in result}
        assert categories == {"security", "performance"}


# ─── Feature 4: Finding feedback ───


class TestFeedbackAPI:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            yield c

    def test_feedback_finding_not_found(self, client):
        response = client.post(
            "/api/dashboard/findings/99999/feedback",
            json={"feedback": "helpful"},
        )
        assert response.status_code == 404

    def test_feedback_invalid_value(self, client):
        response = client.post(
            "/api/dashboard/findings/1/feedback",
            json={"feedback": "invalid_value"},
        )
        assert response.status_code == 400

    def test_feedback_stats_empty(self, client):
        response = client.get("/api/dashboard/analytics/feedback")
        assert response.status_code == 200
        data = response.json()
        assert data["total_rated"] == 0
        assert data["helpful_count"] == 0
        assert data["not_helpful_count"] == 0
        assert data["helpful_rate"] == 0.0
        assert isinstance(data["by_category"], list)


class TestFeedbackModel:
    def test_finding_feedback_enum(self):
        from app.models.review import FindingFeedback
        assert FindingFeedback.HELPFUL == "helpful"
        assert FindingFeedback.NOT_HELPFUL == "not_helpful"

    def test_finding_item_schema_has_feedback(self):
        from app.models.dashboard_schemas import FindingItem
        item = FindingItem(
            id=1,
            file_path="test.py",
            line_start=1,
            line_end=1,
            category="bug",
            severity="warning",
            title="Test",
            description="Test",
            feedback="helpful",
            feedback_note="Great catch!",
        )
        assert item.feedback == "helpful"
        assert item.feedback_note == "Great catch!"

    def test_finding_item_schema_no_feedback(self):
        from app.models.dashboard_schemas import FindingItem
        item = FindingItem(
            id=1,
            file_path="test.py",
            line_start=1,
            line_end=1,
            category="bug",
            severity="warning",
            title="Test",
            description="Test",
        )
        assert item.feedback is None
        assert item.feedback_note is None
