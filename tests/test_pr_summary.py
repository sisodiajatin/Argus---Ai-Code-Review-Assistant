"""Tests for PR auto-summarization feature."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.schemas import AIFinding, FileChange, ReviewChunk
from app.prompts.review import build_pr_summary_prompt
from app.services.review_pipeline import ReviewResult


class TestPRSummaryPrompt:
    def test_builds_prompt_with_all_fields(self):
        prompt = build_pr_summary_prompt(
            pr_title="Add user auth",
            pr_author="jatin",
            base_branch="main",
            files_changed=3,
            additions=100,
            deletions=20,
            file_list="- `auth.py`\n- `login.py`\n- `tests.py`",
            diff_content="some diff content",
        )
        assert "Add user auth" in prompt
        assert "jatin" in prompt
        assert "main" in prompt
        assert "3" in prompt
        assert "+100" in prompt
        assert "-20" in prompt
        assert "auth.py" in prompt
        assert "some diff content" in prompt

    def test_prompt_instructs_neutral_description(self):
        prompt = build_pr_summary_prompt(
            pr_title="Test",
            pr_author="dev",
            base_branch="main",
            files_changed=1,
            additions=10,
            deletions=5,
            file_list="- `test.py`",
            diff_content="diff",
        )
        assert "neutral" in prompt.lower() or "NOT list review findings" in prompt

    def test_prompt_requests_key_changes(self):
        prompt = build_pr_summary_prompt(
            pr_title="Test",
            pr_author="dev",
            base_branch="main",
            files_changed=1,
            additions=10,
            deletions=5,
            file_list="- `test.py`",
            diff_content="diff",
        )
        assert "Key changes" in prompt or "key changes" in prompt.lower()


class TestReviewResultPRDescription:
    def test_review_result_has_pr_description_field(self):
        result = ReviewResult(
            findings=[],
            summary="All good",
            pr_description="This PR adds authentication.",
        )
        assert result.pr_description == "This PR adds authentication."

    def test_review_result_defaults_to_empty(self):
        result = ReviewResult()
        assert result.pr_description == ""


class TestPublisherWithPRDescription:
    def test_summary_includes_pr_description(self):
        from app.services.publisher import ReviewPublisher

        github = MagicMock()
        publisher = ReviewPublisher(github)
        body = publisher._format_summary_comment(
            findings=[],
            summary_text="No issues.",
            pr_description="This PR refactors the login flow to use OAuth2.",
        )
        assert "PR Summary" in body
        assert "OAuth2" in body

    def test_summary_omits_pr_description_when_empty(self):
        from app.services.publisher import ReviewPublisher

        github = MagicMock()
        publisher = ReviewPublisher(github)
        body = publisher._format_summary_comment(
            findings=[],
            summary_text="No issues.",
            pr_description="",
        )
        assert "PR Summary" not in body
