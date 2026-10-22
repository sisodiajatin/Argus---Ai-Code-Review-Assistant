"""A review that could not run must never be reported as clean.

Before this was fixed, an unreachable or misconfigured AI provider produced
"No significant issues found — the code changes look good!", exit code 0 in
the CLI, and a green commit status on GitHub.
"""

import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest
from click.testing import CliRunner

from app.models.schemas import AIFinding, FileChange, ReviewChunk
from app.services.analyzer import AIAnalyzer, ChunkAnalysisError, ReviewIncompleteError
from app.services.review_pipeline import ReviewPipeline
from app.services.vcs.base import PRFile


def _response(content: str, tokens: int = 10):
    return MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))],
        usage=MagicMock(total_tokens=tokens),
    )


def _chunk(chunk_id: str = "c0") -> ReviewChunk:
    return ReviewChunk(
        chunk_id=chunk_id,
        files=[
            FileChange(
                file_path="a.py",
                status="modified",
                additions=1,
                deletions=0,
                patch="@@ -1 +1 @@\n-x = 1\n+x = 2",
            )
        ],
        total_tokens_estimate=10,
    )


@pytest.fixture
def analyzer():
    a = AIAnalyzer()
    a.client = MagicMock()
    return a


class TestAnalyzerFailsClosed:
    async def test_connection_error_raises_after_retries(self, analyzer):
        analyzer.client.chat.completions.create = AsyncMock(
            side_effect=openai.APIConnectionError(request=MagicMock())
        )
        with patch("app.services.analyzer.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ChunkAnalysisError):
                await analyzer.analyze_chunk(_chunk(), "t", "a")
        assert analyzer.client.chat.completions.create.call_count == AIAnalyzer.MAX_RETRIES + 1

    async def test_unparseable_reply_is_a_failure_not_zero_findings(self, analyzer):
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_response("Sorry, I can't help with that.")
        )
        with pytest.raises(ChunkAnalysisError):
            await analyzer.analyze_chunk(_chunk(), "t", "a")

    async def test_valid_empty_findings_is_still_success(self, analyzer):
        analyzer.client.chat.completions.create = AsyncMock(
            return_value=_response('{"findings": [], "summary": "ok"}')
        )
        result = await analyzer.analyze_chunk(_chunk(), "t", "a")
        assert result.findings == []

    async def test_one_failed_chunk_fails_the_whole_review(self, analyzer):
        good = _response(json.dumps({"findings": [], "summary": ""}))
        bad = openai.AuthenticationError(
            message="bad key", response=MagicMock(status_code=401, headers={}), body=None
        )
        analyzer.client.chat.completions.create = AsyncMock(side_effect=[good, bad])
        with pytest.raises(ReviewIncompleteError) as exc:
            await analyzer.analyze_pr([_chunk("c0"), _chunk("c1")], "t", "a")
        assert exc.value.failed == 1
        assert exc.value.total == 2

    async def test_summary_tokens_are_counted(self, analyzer):
        finding = {
            "file_path": "a.py", "line_start": 1, "category": "bug",
            "severity": "warning", "title": "x", "description": "d",
        }
        analyzer.client.chat.completions.create = AsyncMock(
            side_effect=[
                _response(json.dumps({"findings": [finding]}), tokens=100),
                _response("summary text", tokens=40),
            ]
        )
        _, _, tokens, _ = await analyzer.analyze_pr([_chunk()], "t", "a")
        assert tokens == 140

    async def test_duplicate_findings_across_chunks_are_merged(self, analyzer):
        finding = {
            "file_path": "a.py", "line_start": 1, "category": "bug",
            "severity": "warning", "title": "Same issue", "description": "d",
        }
        reply = _response(json.dumps({"findings": [finding]}))
        analyzer.client.chat.completions.create = AsyncMock(
            side_effect=[reply, reply, _response("summary")]
        )
        findings, _, _, _ = await analyzer.analyze_pr([_chunk("c0"), _chunk("c1")], "t", "a")
        assert len(findings) == 1


class TestPipelineFailsClosed:
    async def test_pipeline_propagates_incomplete_review(self):
        pipeline = ReviewPipeline()
        pipeline.chunker.create_chunks = MagicMock(return_value=[_chunk()])
        pipeline.analyzer.analyze_pr = AsyncMock(
            side_effect=ReviewIncompleteError(1, 1, [RuntimeError("boom")])
        )
        pipeline.analyzer.generate_pr_summary_with_usage = AsyncMock(return_value=("", 0))
        files = [PRFile(filename="a.py", status="modified", additions=1, deletions=0,
                        patch="@@ -1 +1 @@\n-x\n+y")]
        with pytest.raises(ReviewIncompleteError):
            await pipeline.run(pr_files=files, title="t", author="a")


@pytest.fixture
def staged_repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "a.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-qm", "init")
    (tmp_path / "a.py").write_text("import subprocess\nsubprocess.call(cmd, shell=True)\n")
    git("add", "a.py")
    return tmp_path


class TestCLIFailsClosed:
    def test_unreachable_provider_exits_2_with_no_clean_report(self, staged_repo, monkeypatch):
        from cli.main import EXIT_REVIEW_FAILED, cli

        monkeypatch.setenv("AI_API_KEY", "sk-test")
        with patch.object(
            AIAnalyzer, "analyze_chunk",
            new=AsyncMock(side_effect=ChunkAnalysisError("c0", ConnectionError("down"))),
        ), patch.object(
            AIAnalyzer, "generate_pr_summary_with_usage", new=AsyncMock(return_value=("", 0)),
        ):
            result = CliRunner().invoke(
                cli, ["review", "-p", str(staged_repo), "-t", "staged", "-f", "json"]
            )

        assert result.exit_code == EXIT_REVIEW_FAILED
        assert "look good" not in result.output
        assert "No significant issues" not in result.output
        assert "review failed" in result.output

    def test_ignore_patterns_reach_the_pipeline(self, staged_repo, monkeypatch):
        from cli.main import cli

        monkeypatch.setenv("AI_API_KEY", "sk-test")
        (staged_repo / ".argus.yaml").write_text('ignore:\n  - "*.lock"\n')
        captured = {}

        async def fake_run(self, **kwargs):
            captured.update(kwargs)
            from app.services.review_pipeline import ReviewResult
            return ReviewResult()

        with patch.object(ReviewPipeline, "run", new=fake_run):
            CliRunner().invoke(
                cli,
                ["review", "-p", str(staged_repo), "-t", "staged", "-f", "json",
                 "--ignore", "docs/*,*.min.js"],
            )
        assert captured["ignored_paths"] == ["*.lock", "docs/*", "*.min.js"]


class TestWebhookPipelineFailsClosed:
    async def _run(self, pipeline_error=None, chunks_processed=1):
        from app.api import webhooks
        from app.models.database import get_session_factory, init_db
        from app.models.pull_request import PRStatus, PullRequest
        from app.models.repository import Repository
        from sqlalchemy import select

        await init_db()
        factory = get_session_factory()
        async with factory() as db:
            repo = Repository(github_id=987654, full_name="o/r", owner="o", name="r",
                              installation_id=1)
            db.add(repo)
            await db.flush()
            pr = PullRequest(repo_id=repo.id, pr_number=1, title="t", author="a",
                             head_sha="deadbeef", status=PRStatus.PENDING.value)
            db.add(pr)
            await db.commit()
            pr_id, repo_id = pr.id, repo.id

        github = MagicMock()
        github.get_pr_files = AsyncMock(return_value=[])
        github.set_commit_status = AsyncMock()

        pipeline = MagicMock()
        pipeline.diff_parser.parse_pr_files = MagicMock(return_value=[])
        if pipeline_error:
            pipeline.run = AsyncMock(side_effect=pipeline_error)
        else:
            from app.services.review_pipeline import ReviewResult
            pipeline.run = AsyncMock(return_value=ReviewResult(chunks_processed=chunks_processed))

        with patch.object(webhooks, "GitHubProvider", return_value=github), \
             patch.object(webhooks, "ReviewPipeline", return_value=pipeline):
            await webhooks._run_review_pipeline(
                db_url="", repo_full_name="o/r", pr_number=1, pr_record_id=pr_id,
                repo_id=repo_id, installation_id=1, pr_title="t", pr_author="a",
                head_sha="deadbeef", base_branch="main", ignored_paths=[],
            )

        async with factory() as db:
            status = (await db.execute(select(PullRequest.status).where(PullRequest.id == pr_id))).scalar_one()
            await db.delete((await db.execute(select(PullRequest).where(PullRequest.id == pr_id))).scalar_one())
            await db.delete((await db.execute(select(Repository).where(Repository.id == repo_id))).scalar_one())
            await db.commit()
        return github.set_commit_status, status

    async def test_incomplete_review_sets_error_status(self):
        set_status, pr_status = await self._run(
            pipeline_error=ReviewIncompleteError(1, 2, [RuntimeError("401")])
        )
        assert set_status.await_args.kwargs["state"] == "error"
        assert "incomplete" in set_status.await_args.kwargs["description"].lower()
        assert pr_status == "failed"

    async def test_no_reviewable_changes_resolves_pending_status(self):
        set_status, pr_status = await self._run(chunks_processed=0)
        assert set_status.await_args.kwargs["state"] == "success"
        assert pr_status == "completed"


def test_findings_model_still_imports():
    # Guard against accidental schema breakage while refactoring the analyzer.
    assert AIFinding(file_path="a", category="bug", severity="warning",
                     title="t", description="d").title == "t"
