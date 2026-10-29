"""Incremental review: re-review only files changed since the last review.

The safety property: the commit status always reflects the WHOLE PR. An
unfixed critical in an untouched file must keep the status red, and a push
that fixes it must clear it.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import AIFinding
from app.services.incremental import plan_incremental_review
from app.services.publisher import ReviewPublisher
from app.services.review_pipeline import ReviewPipeline, ReviewResult
from app.services.vcs.base import PRFile


def prfile(name, prev=None):
    return PRFile(filename=name, status="modified", additions=1, deletions=0,
                  patch="@@ -1 +1 @@\n-old\n+new", previous_filename=prev)


def ai(title, path, severity="critical", line=1):
    return AIFinding(file_path=path, line_start=line, line_end=line, category="security",
                     severity=severity, title=title, description="d")


@pytest.fixture
async def db(tmp_path, monkeypatch):
    from app.models.database import close_db, get_session_factory, init_db
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'inc.db'}")
    await close_db()
    await init_db()
    async with get_session_factory()() as session:
        yield session
    await close_db()


async def seed(db, *, status="completed", findings=(), head_sha="old1111", pr_number=7):
    """A repo with one previous review of `head_sha` holding `findings`."""
    from app.models.pull_request import PullRequest
    from app.models.repository import Repository
    from app.models.review import ReviewFinding, ReviewSummary

    repo = Repository(github_id=9001, full_name="o/r", owner="o", name="r", installation_id=1)
    db.add(repo)
    await db.flush()
    prev = PullRequest(repo_id=repo.id, pr_number=pr_number, title="t", author="a",
                       head_sha=head_sha, status=status, completed_at=datetime.now(timezone.utc))
    db.add(prev)
    await db.flush()
    for path, title, severity, feedback in findings:
        db.add(ReviewFinding(pr_id=prev.id, file_path=path, line_start=1, line_end=1,
                             category="security", severity=severity, title=title,
                             description="d", feedback=feedback))
    db.add(ReviewSummary(pr_id=prev.id, summary_text="previous summary"))
    await db.commit()
    return repo, prev


def github_with_compare(status="ahead", changed=("a.py",), error=None):
    gh = MagicMock()
    if error:
        gh.compare_commits = AsyncMock(side_effect=error)
    else:
        gh.compare_commits = AsyncMock(return_value=(status, list(changed)))
    return gh


async def plan(db, gh, repo, files, head="new2222", pr_number=7):
    return await plan_incremental_review(
        db, gh, repo_full_name="o/r", repo_id=repo.id, pr_number=pr_number,
        head_sha=head, pr_files=files, installation_id=1,
    )


class TestPlanning:
    async def test_reviews_changed_files_and_carries_the_rest(self, db):
        repo, _ = await seed(db, findings=[
            ("a.py", "Old finding in changed file", "warning", None),
            ("b.py", "SQL injection", "critical", None),
            ("b.py", "Rejected noise", "suggestion", "not_helpful"),
        ])
        p = await plan(db, github_with_compare(changed=["a.py"]), repo, [prfile("a.py"), prfile("b.py")])

        assert [f.filename for f in p.review_files] == ["a.py"]
        # a.py's old finding is dropped (it gets re-reviewed); b.py's carried, minus the rejected one
        assert [f.title for f in p.carried_findings] == ["SQL injection"]
        assert p.base_sha == "old1111" and p.total_files == 2
        assert p.previous_summary == "previous summary"

    async def test_no_previous_review_means_full_review(self, db):
        from app.models.repository import Repository
        repo = Repository(github_id=9002, full_name="o/x", owner="o", name="x", installation_id=1)
        db.add(repo)
        await db.commit()
        gh = github_with_compare()
        assert await plan(db, gh, repo, [prfile("a.py")]) is None
        gh.compare_commits.assert_not_called()

    async def test_failed_previous_review_is_not_a_baseline(self, db):
        repo, _ = await seed(db, status="failed")
        assert await plan(db, github_with_compare(), repo, [prfile("a.py")]) is None

    @pytest.mark.parametrize("status", ["diverged", "behind", "identical"])
    async def test_rewritten_history_means_full_review(self, db, status):
        repo, _ = await seed(db)
        assert await plan(db, github_with_compare(status=status), repo, [prfile("a.py")]) is None

    async def test_compare_error_means_full_review(self, db):
        repo, _ = await seed(db)
        gh = github_with_compare(error=RuntimeError("404"))
        assert await plan(db, gh, repo, [prfile("a.py")]) is None

    async def test_huge_compare_means_full_review(self, db):
        repo, _ = await seed(db)
        gh = github_with_compare(changed=[f"f{i}.py" for i in range(300)])
        assert await plan(db, gh, repo, [prfile("a.py")]) is None

    async def test_renamed_file_is_rereviewed(self, db):
        repo, _ = await seed(db, findings=[("old.py", "Issue", "warning", None)])
        p = await plan(db, github_with_compare(changed=["new.py", "old.py"]), repo,
                       [prfile("new.py", prev="old.py"), prfile("c.py")])
        assert [f.filename for f in p.review_files] == ["new.py"]
        assert p.carried_findings == []


async def run_webhook(db, repo, *, files, compare, new_findings, incremental=True, pr_number=7):
    """Run the real background review with GitHub and the model mocked."""
    from app.api import webhooks
    from app.models.pull_request import PullRequest

    pr = PullRequest(repo_id=repo.id, pr_number=pr_number, title="t", author="a",
                     head_sha="new2222", status="pending")
    db.add(pr)
    await db.commit()

    github = MagicMock(get_pr_files=AsyncMock(return_value=files), set_commit_status=AsyncMock(),
                       compare_commits=AsyncMock(return_value=compare))
    pipeline = MagicMock()
    pipeline.settings.ai_model = "m"
    pipeline.run = AsyncMock(return_value=ReviewResult(findings=new_findings, chunks_processed=1,
                                                       summary="new summary"))
    pipeline.diff_parser.parse_pr_files = MagicMock(return_value=[])
    pipeline.diff_parser.commentable_lines = MagicMock(return_value={})
    publisher = MagicMock(publish_review=AsyncMock(return_value=([], 1)))

    with patch.object(webhooks, "GitHubProvider", return_value=github), \
         patch.object(webhooks, "ReviewPipeline", return_value=pipeline), \
         patch.object(webhooks, "ReviewPublisher", return_value=publisher):
        await webhooks._run_review_pipeline(
            db_url="", repo_full_name="o/r", pr_number=pr_number, pr_record_id=pr.id,
            repo_id=repo.id, installation_id=1, pr_title="t", pr_author="a",
            head_sha="new2222", base_branch="main", ignored_paths=[], incremental=incremental,
        )
    final = github.set_commit_status.await_args.kwargs
    return final, pipeline, publisher, github


class TestStatusSafety:
    async def test_unfixed_critical_in_untouched_file_keeps_status_red(self, db):
        repo, _ = await seed(db, findings=[("b.py", "SQL injection", "critical", None)])
        status, pipeline, publisher, _ = await run_webhook(
            db, repo, files=[prfile("a.py"), prfile("b.py")],
            compare=("ahead", ["a.py"]), new_findings=[],
        )
        # Only a.py went to the model...
        assert [f.filename for f in pipeline.run.await_args.kwargs["pr_files"]] == ["a.py"]
        # ...but the PR is still red because b.py's critical is carried over.
        assert status["state"] == "failure"
        assert "1 critical" in status["description"]
        published = publisher.publish_review.await_args.kwargs
        assert [f.title for f in published["findings"]] == ["SQL injection"]
        assert "Incremental review" in published["review_note"]

    async def test_push_that_fixes_the_critical_turns_green(self, db):
        repo, _ = await seed(db, findings=[("a.py", "SQL injection", "critical", None)])
        status, *_ = await run_webhook(
            db, repo, files=[prfile("a.py"), prfile("b.py")],
            compare=("ahead", ["a.py"]), new_findings=[],
        )
        assert status["state"] == "success"

    async def test_carried_findings_are_saved_for_the_next_push(self, db):
        from sqlalchemy import select
        from app.models.pull_request import PullRequest
        from app.models.review import ReviewFinding
        repo, _ = await seed(db, findings=[("b.py", "SQL injection", "critical", None)])
        await run_webhook(db, repo, files=[prfile("a.py"), prfile("b.py")],
                          compare=("ahead", ["a.py"]), new_findings=[ai("New bug", "a.py", "warning")])
        new_pr = (await db.execute(select(PullRequest).where(PullRequest.head_sha == "new2222"))).scalar_one()
        titles = (await db.execute(select(ReviewFinding.title).where(ReviewFinding.pr_id == new_pr.id))).scalars().all()
        assert sorted(titles) == ["New bug", "SQL injection"]

    async def test_nothing_reviewable_changed_skips_model_and_comments(self, db):
        repo, _ = await seed(db, findings=[("b.py", "SQL injection", "critical", None)])
        status, pipeline, publisher, _ = await run_webhook(
            db, repo, files=[prfile("b.py")],
            compare=("ahead", ["docs/notes.md"]), new_findings=[],
        )
        pipeline.run.assert_not_called()
        publisher.publish_review.assert_not_called()
        assert status["state"] == "failure"  # the carried critical still counts

    async def test_force_push_falls_back_to_full_review(self, db):
        repo, _ = await seed(db, findings=[("b.py", "SQL injection", "critical", None)])
        status, pipeline, *_ = await run_webhook(
            db, repo, files=[prfile("a.py"), prfile("b.py")],
            compare=("diverged", ["a.py"]), new_findings=[],
        )
        assert [f.filename for f in pipeline.run.await_args.kwargs["pr_files"]] == ["a.py", "b.py"]
        assert status["state"] == "success"  # full review found nothing; nothing carried

    async def test_not_incremental_never_compares(self, db):
        repo, _ = await seed(db)
        _, pipeline, _, github = await run_webhook(
            db, repo, files=[prfile("a.py")], compare=("ahead", ["a.py"]),
            new_findings=[], incremental=False,
        )
        github.compare_commits.assert_not_called()
        assert pipeline.run.await_args.kwargs.get("description_files") is None


class TestPipelineDescription:
    async def test_pr_description_covers_whole_pr(self):
        pipeline = ReviewPipeline()
        pipeline.analyzer.analyze_pr = AsyncMock(return_value=([], "s", 0, 0.0))
        pipeline.analyzer.generate_pr_summary_with_usage = AsyncMock(return_value=("desc", 0))
        await pipeline.run(pr_files=[prfile("a.py")], title="t", author="a",
                           description_files=[prfile("a.py"), prfile("b.py")])
        chunks = pipeline.analyzer.generate_pr_summary_with_usage.await_args.kwargs["chunks"]
        described = {f.file_path for c in chunks for f in c.files}
        reviewed = {f.file_path for c in pipeline.analyzer.analyze_pr.await_args.kwargs["chunks"] for f in c.files}
        assert described == {"a.py", "b.py"} and reviewed == {"a.py"}


def test_summary_shows_incremental_note():
    body = ReviewPublisher(MagicMock())._format_summary_comment(
        findings=[], summary_text="s", review_note="Incremental review: re-reviewed 1 of 2 files")
    assert "> ℹ️ Incremental review: re-reviewed 1 of 2 files" in body
