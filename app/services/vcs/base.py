"""Abstract base class for Version Control System providers.

This interface allows the review bot to work with multiple VCS platforms.
Currently only GitHub is implemented, but GitLab, Bitbucket, etc. can be
added by implementing this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PRInfo:
    """Platform-agnostic pull request information."""
    number: int
    title: str
    author: str
    head_sha: str
    base_sha: str
    head_branch: str
    base_branch: str
    repo_full_name: str
    repo_id: int
    installation_id: int | None = None


@dataclass
class PRFile:
    """A file changed in a pull request."""
    filename: str
    status: str  # "added", "modified", "removed", "renamed"
    additions: int
    deletions: int
    patch: str | None  # unified diff patch
    previous_filename: str | None = None  # for renames


class VCSProvider(ABC):
    """Abstract base class for VCS platform integrations."""

    @abstractmethod
    async def get_pr_info(self, repo_full_name: str, pr_number: int) -> PRInfo:
        """Fetch pull request metadata."""
        ...

    @abstractmethod
    async def get_pr_files(self, repo_full_name: str, pr_number: int) -> list[PRFile]:
        """Fetch the list of files changed in a PR."""
        ...

    @abstractmethod
    async def get_file_content(self, repo_full_name: str, path: str, ref: str) -> str | None:
        """Fetch the content of a specific file at a given ref/commit."""
        ...

    @abstractmethod
    async def post_review_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        commit_sha: str,
        file_path: str,
        line: int,
        body: str,
        side: str = "RIGHT",
    ) -> int | None:
        """Post an inline review comment on a PR. Returns the comment ID."""
        ...

    @abstractmethod
    async def post_review_summary(
        self,
        repo_full_name: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
    ) -> int | None:
        """Post a top-level review summary on a PR. Returns the review ID.

        Args:
            event: One of "COMMENT", "APPROVE", "REQUEST_CHANGES"
        """
        ...

    @abstractmethod
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify the webhook payload signature for security."""
        ...
