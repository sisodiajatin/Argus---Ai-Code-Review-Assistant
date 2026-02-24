"""Tests for the CLI commands."""

import json
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from click.testing import CliRunner

from cli.main import cli
from app.services.review_pipeline import ReviewResult
from app.models.schemas import AIFinding


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_settings():
    """Create mock CLI settings with test values."""
    settings = MagicMock()
    settings.ai_api_key = "test-key"
    settings.ai_model = "test-model"
    settings.ai_base_url = "https://test.api/v1"
    settings.output_format = "plain"
    settings.database_url = "sqlite:///test.db"
    settings.max_files_per_review = 20
    settings.chunk_token_limit = 8000
    return settings


@pytest.fixture
def sample_result():
    """Create a sample ReviewResult."""
    return ReviewResult(
        findings=[
            AIFinding(
                file_path="test.py",
                line_start=10,
                category="bug",
                severity="warning",
                title="Test issue",
                description="Something to fix",
                suggested_fix="Fix it",
            ),
        ],
        summary="Found 1 issue",
        tokens_used=100,
        processing_time_ms=500.0,
        chunks_processed=1,
        files_reviewed=2,
        model_used="test-model",
    )


class TestCLIVersion:
    def test_version_flag(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestCLIHelp:
    def test_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "All-Seeing Code Reviewer" in result.output

    def test_review_help(self, runner):
        result = runner.invoke(cli, ["review", "--help"])
        assert result.exit_code == 0
        assert "--base" in result.output
        assert "--type" in result.output
        assert "--format" in result.output

    def test_config_help(self, runner):
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0
        assert "show" in result.output
        assert "init" in result.output


class TestConfigShow:
    @patch("cli.main.get_cli_settings")
    def test_config_show(self, mock_get_settings, runner, mock_settings):
        mock_get_settings.return_value = mock_settings
        result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        assert "Argus Configuration" in result.output
        assert "test-model" in result.output


class TestConfigInit:
    def test_config_init(self, runner, tmp_path):
        # Patch pathlib.Path.home to return tmp_path so config goes to a temp dir
        with patch("pathlib.Path.home", return_value=tmp_path):
            result = runner.invoke(cli, ["config", "init"], input="test-key\ntest-model\nhttps://test/v1\n")
            assert result.exit_code == 0
            assert "Config saved" in result.output
            # Verify the file was created
            env_file = tmp_path / ".codereview" / ".env"
            assert env_file.exists()
            content = env_file.read_text()
            assert "AI_API_KEY=test-key" in content


class TestReviewCommand:
    @patch("cli.main.ReviewPipeline")
    @patch("cli.main.LocalGitProvider")
    @patch("cli.main.get_cli_settings")
    def test_review_no_api_key(self, mock_get_settings, mock_git, mock_pipeline, runner):
        settings = MagicMock()
        settings.ai_api_key = ""
        settings.output_format = "plain"
        mock_get_settings.return_value = settings

        result = runner.invoke(cli, ["review"])
        assert result.exit_code != 0
        assert "No AI API key configured" in result.output

    @patch("cli.main.ReviewPipeline")
    @patch("cli.main.LocalGitProvider")
    @patch("cli.main.get_cli_settings")
    def test_review_not_git_repo(self, mock_get_settings, mock_git, mock_pipeline, runner, mock_settings):
        mock_get_settings.return_value = mock_settings
        mock_git.side_effect = ValueError("Not a git repository: /tmp")

        result = runner.invoke(cli, ["review"])
        assert result.exit_code != 0
        assert "Not a git repository" in result.output

    @patch("cli.main.ReviewPipeline")
    @patch("cli.main.LocalGitProvider")
    @patch("cli.main.get_cli_settings")
    def test_review_no_changes(self, mock_get_settings, mock_git, mock_pipeline, runner, mock_settings):
        mock_get_settings.return_value = mock_settings
        mock_instance = MagicMock()
        mock_instance.get_uncommitted_changes.return_value = []
        mock_instance.get_repo_info.return_value = {
            "branch": "main", "remote": "origin", "author": "user"
        }
        mock_git.return_value = mock_instance

        result = runner.invoke(cli, ["review"])
        assert result.exit_code == 0
        assert "No changes found" in result.output

    @patch("cli.main.ReviewPipeline")
    @patch("cli.main.LocalGitProvider")
    @patch("cli.main.get_cli_settings")
    def test_review_with_findings_plain(self, mock_get_settings, mock_git, mock_pipeline, runner, mock_settings, sample_result):
        mock_get_settings.return_value = mock_settings

        # Mock git provider
        mock_git_instance = MagicMock()
        mock_git_instance.get_uncommitted_changes.return_value = [MagicMock()]
        mock_git_instance.get_repo_info.return_value = {
            "branch": "feature", "remote": "origin", "author": "user"
        }
        mock_git.return_value = mock_git_instance

        # Mock pipeline
        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.run = AsyncMock(return_value=sample_result)
        mock_pipeline.return_value = mock_pipeline_instance

        result = runner.invoke(cli, ["review", "--format", "plain"])
        assert result.exit_code == 0
        assert "ARGUS CODE REVIEW" in result.output
        assert "Test issue" in result.output

    @patch("cli.main.ReviewPipeline")
    @patch("cli.main.LocalGitProvider")
    @patch("cli.main.get_cli_settings")
    def test_review_json_format(self, mock_get_settings, mock_git, mock_pipeline, runner, mock_settings, sample_result):
        mock_get_settings.return_value = mock_settings

        mock_git_instance = MagicMock()
        mock_git_instance.get_uncommitted_changes.return_value = [MagicMock()]
        mock_git_instance.get_repo_info.return_value = {
            "branch": "feature", "remote": "origin", "author": "user"
        }
        mock_git.return_value = mock_git_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.run = AsyncMock(return_value=sample_result)
        mock_pipeline.return_value = mock_pipeline_instance

        result = runner.invoke(cli, ["review", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "findings" in data
        assert len(data["findings"]) == 1
        assert data["findings"][0]["title"] == "Test issue"

    @patch("cli.main.ReviewPipeline")
    @patch("cli.main.LocalGitProvider")
    @patch("cli.main.get_cli_settings")
    def test_review_staged_type(self, mock_get_settings, mock_git, mock_pipeline, runner, mock_settings, sample_result):
        mock_get_settings.return_value = mock_settings

        mock_git_instance = MagicMock()
        mock_git_instance.get_staged_changes.return_value = [MagicMock()]
        mock_git_instance.get_repo_info.return_value = {
            "branch": "main", "remote": "origin", "author": "user"
        }
        mock_git.return_value = mock_git_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.run = AsyncMock(return_value=sample_result)
        mock_pipeline.return_value = mock_pipeline_instance

        result = runner.invoke(cli, ["review", "--type", "staged", "--format", "plain"])
        assert result.exit_code == 0
        mock_git_instance.get_staged_changes.assert_called_once()

    @patch("cli.main.ReviewPipeline")
    @patch("cli.main.LocalGitProvider")
    @patch("cli.main.get_cli_settings")
    def test_review_base_branch(self, mock_get_settings, mock_git, mock_pipeline, runner, mock_settings, sample_result):
        mock_get_settings.return_value = mock_settings

        mock_git_instance = MagicMock()
        mock_git_instance.get_branch_diff.return_value = [MagicMock()]
        mock_git_instance.get_repo_info.return_value = {
            "branch": "feature", "remote": "origin", "author": "user"
        }
        mock_git.return_value = mock_git_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.run = AsyncMock(return_value=sample_result)
        mock_pipeline.return_value = mock_pipeline_instance

        result = runner.invoke(cli, ["review", "--base", "develop", "--format", "plain"])
        assert result.exit_code == 0
        mock_git_instance.get_branch_diff.assert_called_once_with("develop")

    @patch("cli.main.ReviewPipeline")
    @patch("cli.main.LocalGitProvider")
    @patch("cli.main.get_cli_settings")
    def test_review_critical_finding_exit_code(self, mock_get_settings, mock_git, mock_pipeline, runner, mock_settings):
        mock_get_settings.return_value = mock_settings

        critical_result = ReviewResult(
            findings=[
                AIFinding(
                    file_path="app.py",
                    line_start=1,
                    category="security",
                    severity="critical",
                    title="SQL Injection",
                    description="User input used in query",
                ),
            ],
            summary="Critical issue found",
            files_reviewed=1,
            model_used="test",
        )

        mock_git_instance = MagicMock()
        mock_git_instance.get_uncommitted_changes.return_value = [MagicMock()]
        mock_git_instance.get_repo_info.return_value = {
            "branch": "main", "remote": "origin", "author": "user"
        }
        mock_git.return_value = mock_git_instance

        mock_pipeline_instance = MagicMock()
        mock_pipeline_instance.run = AsyncMock(return_value=critical_result)
        mock_pipeline.return_value = mock_pipeline_instance

        result = runner.invoke(cli, ["review", "--format", "plain"])
        assert result.exit_code == 1
