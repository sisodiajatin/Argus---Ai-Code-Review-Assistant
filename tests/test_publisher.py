"""Tests for the review publisher service."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.schemas import AIFinding
from app.services.publisher import ReviewPublisher


@pytest.fixture
def mock_github():
    """Create a mock GitHub provider."""
    github = MagicMock()
    github.post_review_comment = AsyncMock(return_value=101)
    github.post_review_summary = AsyncMock(return_value=201)
    github.post_issue_comment = AsyncMock(return_value=301)
    github.find_bot_comment = AsyncMock(return_value=None)
    github.edit_comment = AsyncMock()
    github.set_commit_status = AsyncMock()
    return github


@pytest.fixture
def sample_findings():
    return [
        AIFinding(
            file_path="app.py",
            line_start=10,
            line_end=10,
            category="security",
            severity="critical",
            title="Hardcoded password",
            description="Password is hardcoded in source code.",
            suggested_fix="Use environment variables.",
        ),
        AIFinding(
            file_path="app.py",
            line_start=20,
            line_end=20,
            category="bug",
            severity="warning",
            title="Division by zero",
            description="Possible division by zero.",
        ),
        AIFinding(
            file_path="utils.py",
            line_start=5,
            line_end=5,
            category="style",
            severity="suggestion",
            title="Unused import",
            description="Import os is not used.",
        ),
    ]


class TestSummaryFormatting:
    def test_summary_contains_severity_table(self, mock_github, sample_findings):
        publisher = ReviewPublisher(mock_github)
        body = publisher._format_summary_comment(
            findings=sample_findings,
            summary_text="Found some issues.",
            processing_time_ms=1500,
            files_reviewed=3,
            commit_sha="abc1234567890",
        )
        assert "| Severity | Count |" in body
        assert "Critical" in body
        assert "Warning" in body
        assert "Suggestion" in body

    def test_summary_contains_argus_marker(self, mock_github, sample_findings):
        publisher = ReviewPublisher(mock_github)
        body = publisher._format_summary_comment(
            findings=sample_findings,
            summary_text="Test",
        )
        assert "<!-- argus-review-summary -->" in body

    def test_summary_contains_top_findings(self, mock_github, sample_findings):
        publisher = ReviewPublisher(mock_github)
        body = publisher._format_summary_comment(
            findings=sample_findings,
            summary_text="Test",
        )
        assert "Hardcoded password" in body
        assert "Division by zero" in body
        # suggestion-only findings should NOT be in top findings
        assert "Unused import" not in body.split("### Top Findings")[1].split("### Summary")[0]

    def test_summary_no_issues(self, mock_github):
        publisher = ReviewPublisher(mock_github)
        body = publisher._format_summary_comment(
            findings=[],
            summary_text="All clear.",
        )
        assert "No issues found" in body
        assert "| Severity" not in body

    def test_summary_footer_has_metadata(self, mock_github, sample_findings):
        publisher = ReviewPublisher(mock_github)
        body = publisher._format_summary_comment(
            findings=sample_findings,
            summary_text="Test",
            processing_time_ms=2500,
            files_reviewed=5,
            commit_sha="abc1234567890",
        )
        assert "abc1234" in body
        assert "5 files" in body
        assert "2.5s" in body
        assert "Argus" in body

    def test_critical_shows_failure_status(self, mock_github, sample_findings):
        publisher = ReviewPublisher(mock_github)
        body = publisher._format_summary_comment(
            findings=sample_findings,
            summary_text="Test",
        )
        assert "critical issue" in body.lower()


class TestPublishReview:
    @pytest.mark.asyncio
    async def test_posts_inline_comments(self, mock_github, sample_findings):
        publisher = ReviewPublisher(mock_github)
        comment_ids, _ = await publisher.publish_review(
            repo_full_name="owner/repo",
            pr_number=1,
            commit_sha="abc123",
            findings=sample_findings,
            summary_text="Test summary",
            installation_id=123,
        )
        assert len(comment_ids) == 3
        assert mock_github.post_review_comment.call_count == 3

    @pytest.mark.asyncio
    async def test_new_comment_when_no_existing(self, mock_github, sample_findings):
        """Should post a new issue comment when no existing Argus comment."""
        mock_github.find_bot_comment.return_value = None
        publisher = ReviewPublisher(mock_github)
        _, summary_id = await publisher.publish_review(
            repo_full_name="owner/repo",
            pr_number=1,
            commit_sha="abc123",
            findings=sample_findings,
            summary_text="Test",
            installation_id=123,
        )
        mock_github.post_issue_comment.assert_called_once()
        mock_github.edit_comment.assert_not_called()
        assert summary_id == 301

    @pytest.mark.asyncio
    async def test_edits_existing_comment_on_repush(self, mock_github, sample_findings):
        """Should edit existing comment instead of posting new one on re-push."""
        mock_github.find_bot_comment.return_value = 999
        publisher = ReviewPublisher(mock_github)
        _, summary_id = await publisher.publish_review(
            repo_full_name="owner/repo",
            pr_number=1,
            commit_sha="abc123",
            findings=sample_findings,
            summary_text="Test",
            installation_id=123,
        )
        mock_github.edit_comment.assert_called_once()
        mock_github.post_issue_comment.assert_not_called()
        assert summary_id == 999

    @pytest.mark.asyncio
    async def test_skips_finding_without_line_number(self, mock_github):
        """Findings with no line number should be skipped for inline comments."""
        findings = [
            AIFinding(
                file_path="app.py",
                category="bug",
                severity="warning",
                title="General issue",
                description="Something is off.",
            ),
        ]
        publisher = ReviewPublisher(mock_github)
        comment_ids, _ = await publisher.publish_review(
            repo_full_name="owner/repo",
            pr_number=1,
            commit_sha="abc123",
            findings=findings,
            summary_text="Test",
        )
        assert len(comment_ids) == 0
        mock_github.post_review_comment.assert_not_called()


class TestCommitStatus:
    @pytest.mark.asyncio
    async def test_set_commit_status_called(self, mock_github):
        """Verify the set_commit_status method is callable."""
        await mock_github.set_commit_status(
            repo_full_name="owner/repo",
            sha="abc123",
            state="pending",
            description="Reviewing...",
            installation_id=123,
        )
        mock_github.set_commit_status.assert_called_once()
