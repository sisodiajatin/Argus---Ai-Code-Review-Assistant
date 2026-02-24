"""Tests for the LocalGitProvider."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from app.services.vcs.local_git import LocalGitProvider


def _mock_run(returncode=0, stdout="", stderr=""):
    """Create a mock CompletedProcess."""
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


class TestLocalGitProviderInit:
    @patch("app.services.vcs.local_git.LocalGitProvider._run_git")
    def test_valid_git_repo(self, mock_git):
        mock_git.return_value = _mock_run(stdout="true\n")
        provider = LocalGitProvider("/some/repo")
        assert provider.repo_path == "/some/repo"

    @patch("app.services.vcs.local_git.LocalGitProvider._run_git")
    def test_default_path(self, mock_git):
        mock_git.return_value = _mock_run(stdout="true\n")
        provider = LocalGitProvider()
        assert provider.repo_path == "."

    @patch("app.services.vcs.local_git.LocalGitProvider._run_git")
    def test_invalid_git_repo_raises(self, mock_git):
        mock_git.return_value = _mock_run(returncode=128, stderr="fatal: not a git repo")
        with pytest.raises(ValueError, match="Not a git repository"):
            LocalGitProvider("/not/a/repo")


class TestRenamePath:
    def test_simple_rename(self):
        assert LocalGitProvider._resolve_rename_path("old.py => new.py") == "new.py"

    def test_brace_rename(self):
        assert LocalGitProvider._resolve_rename_path("src/{old.py => new.py}") == "src/new.py"

    def test_nested_brace_rename(self):
        result = LocalGitProvider._resolve_rename_path("a/{b => c}/d.py")
        assert result == "a/c/d.py"

    def test_no_rename(self):
        assert LocalGitProvider._resolve_rename_path("file.py") == "file.py"


class TestNewAndDeletedFileDetection:
    def test_new_file_detected(self):
        patch_lines = ["--- /dev/null", "+++ b/new_file.py", "@@ -0,0 +1,5 @@"]
        assert LocalGitProvider._is_new_file(patch_lines) is True

    def test_existing_file_not_new(self):
        patch_lines = ["--- a/old_file.py", "+++ b/old_file.py", "@@ -1,3 +1,5 @@"]
        assert LocalGitProvider._is_new_file(patch_lines) is False

    def test_deleted_file_detected(self):
        patch_lines = ["--- a/old_file.py", "+++ /dev/null", "@@ -1,5 +0,0 @@"]
        assert LocalGitProvider._is_deleted_file(patch_lines) is True

    def test_modified_file_not_deleted(self):
        patch_lines = ["--- a/file.py", "+++ b/file.py", "@@ -1,3 +1,5 @@"]
        assert LocalGitProvider._is_deleted_file(patch_lines) is False


class TestParseDiffOutput:
    @patch("app.services.vcs.local_git.LocalGitProvider._run_git")
    def _make_provider(self, mock_git):
        mock_git.return_value = _mock_run(stdout="true\n")
        return LocalGitProvider()

    def test_single_modified_file(self):
        provider = self._make_provider()
        diff_text = (
            "diff --git a/app/main.py b/app/main.py\n"
            "--- a/app/main.py\n"
            "+++ b/app/main.py\n"
            "@@ -10,3 +10,4 @@\n"
            " context\n"
            "-old line\n"
            "+new line\n"
            "+added line\n"
        )
        stat_map = {"app/main.py": (2, 1)}

        files = provider._parse_diff_output(diff_text, stat_map)
        assert len(files) == 1
        assert files[0].filename == "app/main.py"
        assert files[0].status == "modified"
        assert files[0].additions == 2
        assert files[0].deletions == 1

    def test_new_file(self):
        provider = self._make_provider()
        diff_text = (
            "diff --git a/new.py b/new.py\n"
            "--- /dev/null\n"
            "+++ b/new.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+line 1\n"
            "+line 2\n"
            "+line 3\n"
        )
        stat_map = {"new.py": (3, 0)}

        files = provider._parse_diff_output(diff_text, stat_map)
        assert len(files) == 1
        assert files[0].filename == "new.py"
        assert files[0].status == "added"

    def test_multiple_files(self):
        provider = self._make_provider()
        diff_text = (
            "diff --git a/a.py b/a.py\n"
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
            "diff --git a/b.py b/b.py\n"
            "--- a/b.py\n"
            "+++ b/b.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        stat_map = {"a.py": (1, 1), "b.py": (1, 1)}

        files = provider._parse_diff_output(diff_text, stat_map)
        assert len(files) == 2
        assert files[0].filename == "a.py"
        assert files[1].filename == "b.py"

    def test_empty_diff(self):
        provider = self._make_provider()
        files = provider._parse_diff_output("", {})
        assert len(files) == 0


class TestGetChangeMethods:
    @patch("app.services.vcs.local_git.LocalGitProvider._run_git")
    def test_get_uncommitted_changes(self, mock_git):
        # First call: _validate_git_repo
        # Then: numstat diff HEAD, diff HEAD
        mock_git.side_effect = [
            _mock_run(stdout="true\n"),  # validate
            _mock_run(stdout="1\t0\tfile.py\n"),  # numstat
            _mock_run(stdout=(
                "diff --git a/file.py b/file.py\n"
                "--- /dev/null\n"
                "+++ b/file.py\n"
                "@@ -0,0 +1 @@\n"
                "+hello\n"
            )),
        ]
        provider = LocalGitProvider()
        files = provider.get_uncommitted_changes()
        assert len(files) == 1
        assert files[0].filename == "file.py"

    @patch("app.services.vcs.local_git.LocalGitProvider._run_git")
    def test_get_staged_changes(self, mock_git):
        mock_git.side_effect = [
            _mock_run(stdout="true\n"),  # validate
            _mock_run(stdout="2\t1\ttest.py\n"),  # numstat --cached
            _mock_run(stdout=(
                "diff --git a/test.py b/test.py\n"
                "--- a/test.py\n"
                "+++ b/test.py\n"
                "@@ -1,3 +1,4 @@\n"
                " line\n"
                "-old\n"
                "+new1\n"
                "+new2\n"
            )),
        ]
        provider = LocalGitProvider()
        files = provider.get_staged_changes()
        assert len(files) == 1
        assert files[0].filename == "test.py"
        assert files[0].status == "modified"

    @patch("app.services.vcs.local_git.LocalGitProvider._run_git")
    def test_get_branch_diff_with_merge_base(self, mock_git):
        mock_git.side_effect = [
            _mock_run(stdout="true\n"),  # validate
            _mock_run(stdout="abc123\n"),  # merge-base
            _mock_run(stdout=""),  # numstat
            _mock_run(stdout=""),  # diff
        ]
        provider = LocalGitProvider()
        files = provider.get_branch_diff("main")
        assert files == []

    @patch("app.services.vcs.local_git.LocalGitProvider._run_git")
    def test_get_branch_diff_no_merge_base(self, mock_git):
        mock_git.side_effect = [
            _mock_run(stdout="true\n"),  # validate
            _mock_run(returncode=1),  # merge-base fails
            _mock_run(stdout=""),  # numstat with base directly
            _mock_run(stdout=""),  # diff
        ]
        provider = LocalGitProvider()
        files = provider.get_branch_diff("main")
        assert files == []


class TestGetRepoInfo:
    @patch("app.services.vcs.local_git.LocalGitProvider._run_git")
    def test_repo_info_success(self, mock_git):
        mock_git.side_effect = [
            _mock_run(stdout="true\n"),  # validate
            _mock_run(stdout="feature-branch\n"),  # branch
            _mock_run(stdout="https://github.com/user/repo.git\n"),  # remote
            _mock_run(stdout="Test User\n"),  # user.name
        ]
        provider = LocalGitProvider()
        info = provider.get_repo_info()
        assert info["branch"] == "feature-branch"
        assert info["remote"] == "https://github.com/user/repo.git"
        assert info["author"] == "Test User"

    @patch("app.services.vcs.local_git.LocalGitProvider._run_git")
    def test_repo_info_fallbacks(self, mock_git):
        mock_git.side_effect = [
            _mock_run(stdout="true\n"),  # validate
            _mock_run(returncode=1),  # branch fails
            _mock_run(returncode=1),  # remote fails
            _mock_run(returncode=1),  # user.name fails
        ]
        provider = LocalGitProvider()
        info = provider.get_repo_info()
        assert info["branch"] == "unknown"
        assert info["remote"] == "local"
        assert info["author"] == "unknown"
