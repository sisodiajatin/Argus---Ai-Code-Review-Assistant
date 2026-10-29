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
    github.create_review = AsyncMock(return_value=55)
    github.list_review_comments = AsyncMock(return_value=[])
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
        # All three go out in ONE review request
        assert len(comment_ids) == 3
        mock_github.create_review.assert_awaited_once()
        assert len(mock_github.create_review.await_args.kwargs["comments"]) == 3
        mock_github.post_review_comment.assert_not_called()

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
        mock_github.create_review.assert_not_called()


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


class TestPublishPlacementAndDedup:
    """Line validation, re-push dedup and the 422 fallback."""

    async def _publish(self, github, findings, commentable=None):
        return await ReviewPublisher(github).publish_review(
            repo_full_name="o/r", pr_number=1, commit_sha="sha",
            findings=findings, summary_text="s", installation_id=1,
            commentable_lines=commentable,
        )

    async def test_findings_outside_diff_go_to_summary(self, mock_github, sample_findings):
        commentable = {"app.py": {10, 11, 12}}  # line 20 and utils.py:5 not in diff
        posted, _ = await self._publish(mock_github, sample_findings, commentable)

        assert len(posted) == 1
        sent = mock_github.create_review.await_args.kwargs["comments"]
        assert [(c["path"], c["line"]) for c in sent] == [("app.py", 10)]
        summary = mock_github.post_issue_comment.await_args.kwargs["body"]
        assert "Not shown inline" in summary
        assert "Division by zero" in summary.split("Not shown inline")[1]
        assert "Unused import" in summary.split("Not shown inline")[1]

    async def test_line_range_snaps_to_first_line_in_diff(self, mock_github):
        finding = AIFinding(file_path="a.py", line_start=3, line_end=8, category="bug",
                            severity="warning", title="t", description="d")
        await self._publish(mock_github, [finding], {"a.py": {6, 7}})
        assert mock_github.create_review.await_args.kwargs["comments"][0]["line"] == 6

    async def test_multiline_finding_anchors_whole_range(self, mock_github):
        finding = AIFinding(file_path="a.py", line_start=4, line_end=6, category="bug",
                            severity="warning", title="t", description="d",
                            suggested_fix="x = compute()\ny = x + 1\nreturn y")
        await self._publish(mock_github, [finding], {"a.py": {4, 5, 6}})
        comment = mock_github.create_review.await_args.kwargs["comments"][0]
        assert (comment["start_line"], comment["line"]) == (4, 6)
        assert "```suggestion" in comment["body"]

    async def test_already_posted_findings_are_not_reposted(self, mock_github, sample_findings):
        await self._publish(mock_github, sample_findings)
        first_bodies = [c["body"] for c in mock_github.create_review.await_args.kwargs["comments"]]

        # Second push: GitHub now holds those comments
        mock_github.create_review.reset_mock()
        mock_github.list_review_comments.return_value = [{"body": b} for b in first_bodies]
        posted, _ = await self._publish(mock_github, sample_findings)

        assert posted == []
        mock_github.create_review.assert_not_called()

    async def test_new_finding_still_posted_on_repush(self, mock_github, sample_findings):
        await self._publish(mock_github, sample_findings[:2])
        bodies = [c["body"] for c in mock_github.create_review.await_args.kwargs["comments"]]
        mock_github.create_review.reset_mock()
        mock_github.list_review_comments.return_value = [{"body": b} for b in bodies]

        posted, _ = await self._publish(mock_github, sample_findings)

        sent = mock_github.create_review.await_args.kwargs["comments"]
        assert len(posted) == 1
        assert sent[0]["path"] == "utils.py"

    async def test_rejected_batch_falls_back_to_individual_comments(self, mock_github, sample_findings):
        import httpx
        request = httpx.Request("POST", "https://api.github.com/x")
        mock_github.create_review.side_effect = httpx.HTTPStatusError(
            "422", request=request, response=httpx.Response(422, request=request)
        )
        mock_github.post_review_comment.side_effect = [101, None, 103]  # middle one rejected

        posted, _ = await self._publish(mock_github, sample_findings)

        assert mock_github.post_review_comment.await_count == 3
        assert len(posted) == 2


class TestCommentableLines:
    def test_added_and_context_lines_are_commentable(self):
        from app.services.diff_parser import DiffParser
        from app.services.vcs.base import PRFile

        patch_text = "@@ -1,3 +1,4 @@\n ctx1\n-old\n+new1\n+new2\n ctx2"
        files = DiffParser().parse_pr_files([PRFile(filename="a.py", status="modified",
                                                    additions=2, deletions=1, patch=patch_text)])
        assert DiffParser.commentable_lines(files) == {"a.py": {1, 2, 3, 4}}


class TestSuggestionBlocksAreCodeOnly:
    """GitHub applies a ```suggestion block verbatim, so it must hold only code.

    Regression: the model answered "Replace pickle ... Example using JSON:" plus a
    fenced block, and the whole markdown answer was put inside a suggestion block,
    so "Apply suggestion" would have pasted the explanation into the source file.
    """

    LIVE_ANSWER = (
        "Replace pickle deserialization with a safe format (e.g., JSON) or add strict "
        "validation before unpickling. Example using JSON:\n"
        "```python\nimport json\n\ndef load_session(blob: bytes) -> dict:\n"
        "    return json.loads(blob.decode('utf-8'))\n```"
    )

    def _body(self, fix):
        finding = AIFinding(file_path="b.py", line_start=7, category="security",
                            severity="critical", title="t", description="d", suggested_fix=fix)
        return ReviewPublisher(MagicMock())._format_finding_comment(finding)

    def test_prose_plus_fence_is_rendered_as_markdown(self):
        body = self._body(self.LIVE_ANSWER)
        assert "```suggestion" not in body
        assert "**Suggested fix:**" in body
        assert "```python" in body  # the code still renders as a code block

    def test_single_fenced_block_is_unwrapped_into_a_suggestion(self):
        body = self._body("```python\nreturn json.loads(blob)\n```")
        assert "```suggestion\nreturn json.loads(blob)\n```" in body
        assert "```python" not in body

    @pytest.mark.parametrize("fix", [
        "Move the API key to an environment variable instead of hardcoding it.",
        "```py\na = 1\n```\n```py\nb = 2\n```",
        "Use parameters, for example:\ncursor.execute(sql, (uid,))",
    ])
    def test_non_code_fixes_never_become_suggestions(self, fix):
        assert "```suggestion" not in self._body(fix)

    @pytest.mark.parametrize("fix", [
        "data = json.loads(blob)\nreturn data",
        "# Use query parameters\ncursor.execute(\"SELECT * FROM t WHERE id = ?\", (uid,))",
        'def f(x):\n    """Return the double of x."""\n    return x * 2',
    ])
    def test_pure_code_still_becomes_a_suggestion(self, fix):
        assert "```suggestion" in self._body(fix)
