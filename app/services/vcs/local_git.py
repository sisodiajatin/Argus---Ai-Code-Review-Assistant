"""Local git provider for CLI-based code review.

Wraps subprocess git commands to produce PRFile objects compatible
with the existing review pipeline. Supports uncommitted, staged,
branch diff, and committed change types.
"""

import logging
import subprocess
from pathlib import Path

from app.services.vcs.base import PRFile

logger = logging.getLogger(__name__)


class LocalGitProvider:
    """Extracts diffs from a local git repository as PRFile objects."""

    def __init__(self, repo_path: str | None = None):
        self.repo_path = repo_path or "."
        self._validate_git_repo()

    def _validate_git_repo(self):
        """Ensure the path is a valid git repository."""
        result = self._run_git("rev-parse", "--is-inside-work-tree")
        if result.returncode != 0:
            raise ValueError(f"Not a git repository: {self.repo_path}")

    def _run_git(self, *args: str) -> subprocess.CompletedProcess:
        """Run a git command and return the result."""
        cmd = ["git", "-C", self.repo_path, *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def get_uncommitted_changes(self) -> list[PRFile]:
        """Get all uncommitted changes (both staged and unstaged)."""
        return self._diff_to_pr_files("HEAD")

    def get_staged_changes(self) -> list[PRFile]:
        """Get only staged (git add) changes."""
        return self._diff_to_pr_files("--cached")

    def get_branch_diff(self, base: str = "main") -> list[PRFile]:
        """Get diff between current branch and a base branch."""
        # Find the merge base to only get changes on this branch
        merge_base = self._run_git("merge-base", base, "HEAD")
        if merge_base.returncode != 0:
            logger.warning(f"Could not find merge-base with {base}, using {base} directly")
            return self._diff_to_pr_files(base)
        return self._diff_to_pr_files(merge_base.stdout.strip())

    def get_committed_changes(self, base: str = "main") -> list[PRFile]:
        """Get committed but unpushed changes vs a base branch."""
        return self.get_branch_diff(base)

    def _diff_to_pr_files(self, *diff_args: str) -> list[PRFile]:
        """Run git diff with args and convert to PRFile objects."""
        # Get the numstat for additions/deletions counts
        stat_result = self._run_git("diff", "--numstat", *diff_args)
        stat_map: dict[str, tuple[int, int]] = {}
        if stat_result.returncode == 0:
            for line in stat_result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    adds = int(parts[0]) if parts[0] != "-" else 0
                    dels = int(parts[1]) if parts[1] != "-" else 0
                    filename = parts[2]
                    # Handle renames: "old => new" or "{old => new}/path"
                    if " => " in filename:
                        filename = self._resolve_rename_path(filename)
                    stat_map[filename] = (adds, dels)

        # Get the actual diff patches per file
        diff_result = self._run_git("diff", "--unified=5", *diff_args)
        if diff_result.returncode != 0:
            logger.error(f"git diff failed: {diff_result.stderr}")
            return []

        return self._parse_diff_output(diff_result.stdout, stat_map)

    def _parse_diff_output(
        self,
        diff_text: str,
        stat_map: dict[str, tuple[int, int]],
    ) -> list[PRFile]:
        """Parse unified diff output into PRFile objects."""
        files: list[PRFile] = []
        current_file: str | None = None
        current_patch_lines: list[str] = []
        old_file: str | None = None

        for line in diff_text.split("\n"):
            if line.startswith("diff --git"):
                # Save previous file
                if current_file is not None:
                    files.append(self._build_pr_file(
                        current_file, old_file, current_patch_lines, stat_map
                    ))
                # Parse new file path from "diff --git a/path b/path"
                parts = line.split(" b/", 1)
                current_file = parts[1] if len(parts) > 1 else None
                old_file = None
                current_patch_lines = []

            elif line.startswith("rename from "):
                old_file = line[len("rename from "):]

            elif line.startswith("--- ") or line.startswith("+++ ") or line.startswith("@@") or \
                 line.startswith("+") or line.startswith("-") or line.startswith(" "):
                current_patch_lines.append(line)

        # Save last file
        if current_file is not None:
            files.append(self._build_pr_file(
                current_file, old_file, current_patch_lines, stat_map
            ))

        return files

    def _build_pr_file(
        self,
        filename: str,
        old_filename: str | None,
        patch_lines: list[str],
        stat_map: dict[str, tuple[int, int]],
    ) -> PRFile:
        """Build a PRFile from parsed diff data."""
        adds, dels = stat_map.get(filename, (0, 0))
        patch = "\n".join(patch_lines)

        # Determine status
        if old_filename:
            status = "renamed"
        elif adds > 0 and dels == 0 and self._is_new_file(patch_lines):
            status = "added"
        elif adds == 0 and dels > 0 and self._is_deleted_file(patch_lines):
            status = "removed"
        else:
            status = "modified"

        return PRFile(
            filename=filename,
            status=status,
            additions=adds,
            deletions=dels,
            patch=patch,
            previous_filename=old_filename,
        )

    @staticmethod
    def _is_new_file(patch_lines: list[str]) -> bool:
        """Check if the patch represents a newly created file."""
        for line in patch_lines:
            if line.startswith("--- /dev/null"):
                return True
        return False

    @staticmethod
    def _is_deleted_file(patch_lines: list[str]) -> bool:
        """Check if the patch represents a deleted file."""
        for line in patch_lines:
            if line.startswith("+++ /dev/null"):
                return True
        return False

    @staticmethod
    def _resolve_rename_path(path: str) -> str:
        """Resolve git's rename path notation.

        Examples:
            "old.py => new.py" -> "new.py"
            "src/{old.py => new.py}" -> "src/new.py"
        """
        if "{" in path:
            # Handle "prefix/{old => new}/suffix" format
            import re
            match = re.search(r"(.*)\{.* => (.*?)\}(.*)", path)
            if match:
                return match.group(1) + match.group(2) + match.group(3)
        if " => " in path:
            return path.split(" => ")[1]
        return path

    def get_repo_info(self) -> dict:
        """Get basic repository information."""
        branch = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        remote = self._run_git("remote", "get-url", "origin")
        user = self._run_git("config", "user.name")

        return {
            "branch": branch.stdout.strip() if branch.returncode == 0 else "unknown",
            "remote": remote.stdout.strip() if remote.returncode == 0 else "local",
            "author": user.stdout.strip() if user.returncode == 0 else "unknown",
        }
