"""Feedback loop: findings a repo's reviewers rejected are not raised again."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import AIFinding
from app.prompts.review import build_review_prompt
from app.services.feedback import (
    FeedbackMemory,
    FeedbackPattern,
    apply_feedback,
    build_feedback_hint,
    load_feedback_memory,
    title_similarity,
)
from app.services.publisher import ReviewPublisher
from app.services.review_pipeline import ReviewPipeline
from app.services.vcs.base import PRFile


def finding(title, category="bug", severity="warning", path="a.py", line=1):
    return AIFinding(file_path=path, line_start=line, line_end=line, category=category,
                     severity=severity, title=title, description="d")


REJECTED = FeedbackMemory(rejected=[
    FeedbackPattern("bug", "Reference to non-existent action version", "v7 exists"),
    FeedbackPattern("style", "Specify file encoding explicitly"),
])


class TestSimilarity:
    def test_rephrased_titles_match(self):
        assert title_similarity(
            "Reference to non-existent action version",
            "Non-existent action versions referenced",
        ) >= 0.6

    def test_unrelated_titles_do_not_match(self):
        assert title_similarity("SQL injection in find_user", "Specify file encoding") < 0.3

    def test_plural_and_case_insensitive(self):
        assert title_similarity("Hardcoded Credentials", "hardcoded credential") == 1.0


class TestApplyFeedback:
    def test_rejected_warning_is_suppressed(self):
        kept, hidden = apply_feedback([finding("Reference to non-existent action version")], REJECTED)
        assert kept == [] and len(hidden) == 1

    def test_same_title_different_category_is_kept(self):
        kept, hidden = apply_feedback(
            [finding("Reference to non-existent action version", category="security")], REJECTED)
        assert len(kept) == 1 and hidden == []

    def test_critical_findings_are_never_suppressed(self):
        kept, hidden = apply_feedback(
            [finding("Reference to non-existent action version", severity="critical")], REJECTED)
        assert len(kept) == 1 and hidden == []

    def test_conflicting_helpful_feedback_keeps_finding(self):
        memory = FeedbackMemory(
            rejected=[FeedbackPattern("style", "Specify file encoding explicitly")],
            accepted=[FeedbackPattern("style", "Specify the file encoding explicitly")],
        )
        kept, hidden = apply_feedback(
            [finding("Specify file encoding explicitly", category="style", severity="suggestion")], memory)
        assert len(kept) == 1 and hidden == []

    def test_unrelated_findings_pass_through(self):
        findings = [finding("Division by zero on empty list")]
        assert apply_feedback(findings, REJECTED) == (findings, [])

    def test_no_memory_is_a_noop(self):
        findings = [finding("anything")]
        assert apply_feedback(findings, None) == (findings, [])
        assert apply_feedback(findings, FeedbackMemory()) == (findings, [])


class TestPromptHint:
    def test_hint_lists_rejected_patterns_with_notes(self):
        hint = build_feedback_hint(REJECTED)
        assert "[bug] Reference to non-existent action version (reviewer note: v7 exists)" in hint
        assert "[style] Specify file encoding explicitly" in hint

    def test_hint_deduplicates_and_caps(self):
        memory = FeedbackMemory(rejected=[FeedbackPattern("bug", "Same")] * 5
                                + [FeedbackPattern("bug", f"T{i}") for i in range(40)])
        lines = build_feedback_hint(memory).splitlines()
        assert lines.count("- [bug] Same") == 1
        assert len(lines) == 15

    def test_empty_memory_gives_no_hint(self):
        assert build_feedback_hint(None) == "" and build_feedback_hint(FeedbackMemory()) == ""

    def test_review_prompt_fences_the_hint(self):
        prompt = build_review_prompt("t", "a", "+x", feedback_hint=build_feedback_hint(REJECTED))
        assert "marked the following past findings as NOT helpful" in prompt
        assert "<untrusted_rejected_findings" in prompt

    def test_review_prompt_unchanged_without_feedback(self):
        assert "NOT helpful" not in build_review_prompt("t", "a", "+x")


def _response(content, tokens=10):
    return MagicMock(choices=[MagicMock(message=MagicMock(content=content))],
                     usage=MagicMock(total_tokens=tokens))


class TestPipelineWithFeedback:
    async def test_rejected_finding_is_removed_before_summary(self):
        raw = {"findings": [
            {"file_path": "a.py", "line_start": 1, "category": "bug", "severity": "warning",
             "title": "Reference to non-existent action version", "description": "d"},
            {"file_path": "a.py", "line_start": 2, "category": "security", "severity": "critical",
             "title": "SQL injection", "description": "d"},
        ]}
        pipeline = ReviewPipeline()
        async def reply(**kwargs):
            # Review calls ask for JSON; summary and PR-description calls don't.
            # They run concurrently, so answer by request type, not by order.
            if kwargs.get("response_format"):
                return _response(json.dumps(raw))
            return _response("text")

        create = AsyncMock(side_effect=reply)
        pipeline.analyzer.client = MagicMock()
        pipeline.analyzer.client.chat.completions.create = create

        files = [PRFile(filename="a.py", status="modified", additions=2, deletions=0,
                        patch="@@ -1,0 +1,2 @@\n+a\n+b")]
        result = await pipeline.run(pr_files=files, title="t", author="a", feedback=REJECTED)

        assert [f.title for f in result.findings] == ["SQL injection"]
        assert [f.title for f in result.suppressed_findings] == ["Reference to non-existent action version"]
        # The review prompt told the model, and the summary never saw the hidden finding
        calls = [c.kwargs for c in create.await_args_list]
        review_prompt = next(c["messages"][-1]["content"] for c in calls if c.get("response_format"))
        assert "NOT helpful" in review_prompt
        summary_prompt = next(c["messages"][-1]["content"] for c in calls
                              if "Individual Findings" in c["messages"][-1]["content"])
        assert "non-existent action version" not in summary_prompt
        assert "SQL injection" in summary_prompt


class TestSummaryComment:
    def test_hidden_findings_are_listed_not_dropped(self):
        body = ReviewPublisher(MagicMock())._format_summary_comment(
            findings=[], summary_text="s",
            suppressed_findings=[finding("Specify file encoding explicitly", category="style")],
        )
        assert "🔕 1 finding hidden" in body
        assert "Specify file encoding explicitly" in body
        assert "<details>" in body

    def test_no_section_without_hidden_findings(self):
        body = ReviewPublisher(MagicMock())._format_summary_comment(findings=[], summary_text="s")
        assert "🔕" not in body


@pytest.fixture
async def db(tmp_path, monkeypatch):
    """An isolated database, so seeded feedback can't leak into other tests."""
    from app.models.database import close_db, get_session_factory, init_db
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'feedback.db'}")
    await close_db()
    await init_db()
    async with get_session_factory()() as session:
        yield session
    await close_db()


async def _seed(db, github_id, name, rated):
    """Create a repo with one reviewed PR whose findings carry the given feedback."""
    from datetime import datetime, timedelta, timezone
    from app.models.pull_request import PullRequest
    from app.models.repository import Repository
    from app.models.review import ReviewFinding

    repo = Repository(github_id=github_id, full_name=name, owner="o", name=name, installation_id=1)
    db.add(repo)
    await db.flush()
    pr = PullRequest(repo_id=repo.id, pr_number=1, title="t", author="a", head_sha=f"sha{github_id}")
    db.add(pr)
    await db.flush()
    now = datetime.now(timezone.utc)
    for i, (title, category, fb) in enumerate(rated):
        db.add(ReviewFinding(pr_id=pr.id, file_path="a.py", category=category, severity="warning",
                             title=title, description="d", feedback=fb,
                             feedback_at=now - timedelta(minutes=i) if fb else None))
    await db.commit()
    return repo


class TestLoadFeedbackMemory:
    async def test_scoped_to_repo_and_split_by_rating(self, db):
        mine = await _seed(db, 5001, "o/mine", [
            ("Specify file encoding explicitly", "style", "not_helpful"),
            ("SQL injection", "security", "helpful"),
            ("Unrated finding", "bug", None),
        ])
        await _seed(db, 5002, "o/other", [("Other repo rejection", "bug", "not_helpful")])

        memory = await load_feedback_memory(db, mine.id)

        assert [p.title for p in memory.rejected] == ["Specify file encoding explicitly"]
        assert [p.title for p in memory.accepted] == ["SQL injection"]


class TestWebhookUsesFeedback:
    async def test_pipeline_receives_repo_feedback(self, db):
        from app.api import webhooks
        from app.models.pull_request import PullRequest
        from app.services.review_pipeline import ReviewResult

        repo = await _seed(db, 5003, "o/hooked", [("Missing docstring", "style", "not_helpful")])
        pr = PullRequest(repo_id=repo.id, pr_number=2, title="t", author="a", head_sha="newsha")
        db.add(pr)
        await db.commit()

        github = MagicMock(get_pr_files=AsyncMock(return_value=[]), set_commit_status=AsyncMock())
        pipeline = MagicMock()
        pipeline.run = AsyncMock(return_value=ReviewResult(chunks_processed=0))
        pipeline.diff_parser.parse_pr_files = MagicMock(return_value=[])

        with patch.object(webhooks, "GitHubProvider", return_value=github), \
             patch.object(webhooks, "ReviewPipeline", return_value=pipeline):
            await webhooks._run_review_pipeline(
                db_url="", repo_full_name="o/hooked", pr_number=2, pr_record_id=pr.id,
                repo_id=repo.id, installation_id=1, pr_title="t", pr_author="a",
                head_sha="newsha", base_branch="main", ignored_paths=[],
            )

        feedback = pipeline.run.await_args.kwargs["feedback"]
        assert [p.title for p in feedback.rejected] == ["Missing docstring"]
