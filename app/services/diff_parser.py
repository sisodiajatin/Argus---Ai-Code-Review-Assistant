"""Diff parser service.

Parses unified diff format (as returned by GitHub API) into structured
FileChange objects with hunks and line-level detail, enabling accurate
mapping of review comments to specific lines.
"""

import logging
import re

from app.models.schemas import FileChange, DiffHunk, DiffLine
from app.services.vcs.base import PRFile

logger = logging.getLogger(__name__)


class DiffParser:
    """Parses unified diffs into structured representations."""

    # Regex to match hunk headers like: @@ -10,5 +20,8 @@ optional context
    HUNK_HEADER_RE = re.compile(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$"
    )

    def parse_pr_files(self, pr_files: list[PRFile]) -> list[FileChange]:
        """Parse a list of PR files into structured FileChange objects.

        Args:
            pr_files: List of PRFile objects from the VCS provider.

        Returns:
            List of FileChange objects with parsed hunks and lines.
        """
        file_changes = []
        for pr_file in pr_files:
            try:
                file_change = self._parse_single_file(pr_file)
                file_changes.append(file_change)
            except Exception as e:
                logger.warning(f"Failed to parse diff for {pr_file.filename}: {e}")
                # Still include the file with basic info, just no parsed hunks
                file_changes.append(
                    FileChange(
                        file_path=pr_file.filename,
                        status=pr_file.status,
                        old_path=pr_file.previous_filename,
                        additions=pr_file.additions,
                        deletions=pr_file.deletions,
                        patch=pr_file.patch or "",
                    )
                )
        return file_changes

    def _parse_single_file(self, pr_file: PRFile) -> FileChange:
        """Parse a single file's diff into a FileChange object."""
        hunks = []
        if pr_file.patch:
            hunks = self._parse_patch(pr_file.patch)

        return FileChange(
            file_path=pr_file.filename,
            status=pr_file.status,
            old_path=pr_file.previous_filename,
            additions=pr_file.additions,
            deletions=pr_file.deletions,
            patch=pr_file.patch or "",
            hunks=hunks,
        )

    def _parse_patch(self, patch: str) -> list[DiffHunk]:
        """Parse a unified diff patch into a list of DiffHunk objects.

        Args:
            patch: The raw unified diff patch text.

        Returns:
            List of DiffHunk objects with parsed lines.
        """
        hunks = []
        current_hunk = None
        old_line = 0
        new_line = 0

        for line in patch.split("\n"):
            # Check for hunk header
            match = self.HUNK_HEADER_RE.match(line)
            if match:
                # Save previous hunk if exists
                if current_hunk is not None:
                    hunks.append(current_hunk)

                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1
                header = match.group(5).strip()

                current_hunk = DiffHunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    header=header,
                    lines=[],
                )
                old_line = old_start
                new_line = new_start
                continue

            if current_hunk is None:
                continue

            # Parse diff lines
            if line.startswith("+"):
                current_hunk.lines.append(
                    DiffLine(
                        content=line[1:],
                        line_type="add",
                        old_line_number=None,
                        new_line_number=new_line,
                    )
                )
                new_line += 1
            elif line.startswith("-"):
                current_hunk.lines.append(
                    DiffLine(
                        content=line[1:],
                        line_type="delete",
                        old_line_number=old_line,
                        new_line_number=None,
                    )
                )
                old_line += 1
            elif line.startswith("\\"):
                # "\ No newline at end of file" - skip
                continue
            else:
                # Context line (starts with space or is empty)
                content = line[1:] if line.startswith(" ") else line
                current_hunk.lines.append(
                    DiffLine(
                        content=content,
                        line_type="context",
                        old_line_number=old_line,
                        new_line_number=new_line,
                    )
                )
                old_line += 1
                new_line += 1

        # Don't forget the last hunk
        if current_hunk is not None:
            hunks.append(current_hunk)

        return hunks

    def get_changed_line_numbers(self, file_change: FileChange) -> list[int]:
        """Get all new (added/modified) line numbers from a file change.

        These are the line numbers in the new version of the file where
        changes were made - useful for mapping review comments.
        """
        changed_lines = []
        for hunk in file_change.hunks:
            for line in hunk.lines:
                if line.line_type == "add" and line.new_line_number is not None:
                    changed_lines.append(line.new_line_number)
        return changed_lines

    def format_diff_for_llm(self, file_change: FileChange) -> str:
        """Format a file change into a readable string for LLM analysis.

        Produces a compact but informative representation that includes
        file metadata and the actual diff content.
        """
        parts = [
            f"## File: {file_change.file_path}",
            f"Status: {file_change.status} | +{file_change.additions} -{file_change.deletions}",
        ]

        if file_change.old_path:
            parts.append(f"Renamed from: {file_change.old_path}")

        parts.append("")  # blank line

        for hunk in file_change.hunks:
            if hunk.header:
                parts.append(f"### {hunk.header}")

            for line in hunk.lines:
                prefix = {"add": "+", "delete": "-", "context": " "}.get(line.line_type, " ")
                line_num = line.new_line_number or line.old_line_number or ""
                parts.append(f"{prefix} {line_num:>4}| {line.content}")

            parts.append("")  # blank line between hunks

        return "\n".join(parts)
