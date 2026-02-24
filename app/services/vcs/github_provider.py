"""GitHub VCS provider implementation.

Uses PyGithub for API interactions and handles GitHub App authentication
with installation tokens.
"""

import hashlib
import hmac
import logging
import time

import httpx
import jwt
from github import Github, GithubIntegration, Auth

from app.config import get_settings
from app.services.vcs.base import VCSProvider, PRInfo, PRFile

logger = logging.getLogger(__name__)


class GitHubProvider(VCSProvider):
    """GitHub VCS provider using GitHub App authentication."""

    def __init__(self):
        self.settings = get_settings()
        self._integration: GithubIntegration | None = None
        self._installation_tokens: dict[int, tuple[str, float]] = {}  # installation_id -> (token, expires_at)

    def _read_private_key(self) -> str:
        """Read GitHub App private key from env var or file."""
        # Prefer env var (for cloud deployment like Render/Railway)
        if self.settings.github_private_key:
            return self.settings.github_private_key
        # Fall back to file path (for local dev / Docker with mounted file)
        with open(self.settings.github_private_key_path, "r") as f:
            return f.read()

    def _get_integration(self) -> GithubIntegration:
        """Get or create the GitHub App integration."""
        if self._integration is None:
            private_key = self._read_private_key()

            auth = Auth.AppAuth(
                app_id=int(self.settings.github_app_id),
                private_key=private_key,
            )
            self._integration = GithubIntegration(auth=auth)
        return self._integration

    def _get_github_client(self, installation_id: int) -> Github:
        """Get an authenticated GitHub client for a specific installation."""
        integration = self._get_integration()
        return integration.get_github_for_installation(installation_id)

    async def _get_installation_token(self, installation_id: int) -> str:
        """Get or refresh an installation access token."""
        now = time.time()

        # Check if we have a cached, non-expired token
        if installation_id in self._installation_tokens:
            token, expires_at = self._installation_tokens[installation_id]
            if now < expires_at - 60:  # 60s buffer before expiry
                return token

        # Generate a new JWT
        private_key = self._read_private_key()

        payload = {
            "iat": int(now) - 60,
            "exp": int(now) + (10 * 60),
            "iss": self.settings.github_app_id,
        }
        encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")

        # Exchange JWT for installation token
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {encoded_jwt}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            data = response.json()

        token = data["token"]
        expires_at = now + 3600  # Tokens are valid for 1 hour
        self._installation_tokens[installation_id] = (token, expires_at)
        return token

    async def _make_api_request(
        self,
        method: str,
        url: str,
        installation_id: int,
        json_data: dict | None = None,
    ) -> dict | list:
        """Make an authenticated API request to GitHub."""
        token = await self._get_installation_token(installation_id)
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=f"https://api.github.com{url}",
                headers=headers,
                json=json_data,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def get_pr_info(
        self,
        repo_full_name: str,
        pr_number: int,
        installation_id: int | None = None,
    ) -> PRInfo:
        """Fetch pull request metadata from GitHub."""
        data = await self._make_api_request(
            "GET",
            f"/repos/{repo_full_name}/pulls/{pr_number}",
            installation_id=installation_id or 0,
        )
        return PRInfo(
            number=data["number"],
            title=data["title"],
            author=data["user"]["login"],
            head_sha=data["head"]["sha"],
            base_sha=data["base"]["sha"],
            head_branch=data["head"]["ref"],
            base_branch=data["base"]["ref"],
            repo_full_name=repo_full_name,
            repo_id=data["base"]["repo"]["id"],
            installation_id=installation_id,
        )

    async def get_pr_files(
        self,
        repo_full_name: str,
        pr_number: int,
        installation_id: int | None = None,
    ) -> list[PRFile]:
        """Fetch the list of files changed in a PR."""
        data = await self._make_api_request(
            "GET",
            f"/repos/{repo_full_name}/pulls/{pr_number}/files",
            installation_id=installation_id or 0,
        )
        files = []
        for file_data in data:
            files.append(
                PRFile(
                    filename=file_data["filename"],
                    status=file_data["status"],
                    additions=file_data.get("additions", 0),
                    deletions=file_data.get("deletions", 0),
                    patch=file_data.get("patch"),
                    previous_filename=file_data.get("previous_filename"),
                )
            )
        return files

    async def get_file_content(
        self,
        repo_full_name: str,
        path: str,
        ref: str,
        installation_id: int | None = None,
    ) -> str | None:
        """Fetch the content of a specific file at a given ref."""
        try:
            token = await self._get_installation_token(installation_id or 0)
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.github.com/repos/{repo_full_name}/contents/{path}",
                    params={"ref": ref},
                    headers={
                        "Authorization": f"token {token}",
                        "Accept": "application/vnd.github.raw+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=30.0,
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.text
        except Exception as e:
            logger.warning(f"Failed to fetch file content {path}@{ref}: {e}")
            return None

    async def post_review_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        commit_sha: str,
        file_path: str,
        line: int,
        body: str,
        side: str = "RIGHT",
        installation_id: int | None = None,
    ) -> int | None:
        """Post an inline review comment on a GitHub PR."""
        try:
            data = await self._make_api_request(
                "POST",
                f"/repos/{repo_full_name}/pulls/{pr_number}/comments",
                installation_id=installation_id or 0,
                json_data={
                    "body": body,
                    "commit_id": commit_sha,
                    "path": file_path,
                    "line": line,
                    "side": side,
                },
            )
            return data.get("id")
        except Exception as e:
            logger.error(f"Failed to post review comment on {file_path}:{line}: {e}")
            return None

    async def post_review_summary(
        self,
        repo_full_name: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
        installation_id: int | None = None,
    ) -> int | None:
        """Post a review summary on a GitHub PR."""
        try:
            data = await self._make_api_request(
                "POST",
                f"/repos/{repo_full_name}/pulls/{pr_number}/reviews",
                installation_id=installation_id or 0,
                json_data={
                    "body": body,
                    "event": event,
                },
            )
            return data.get("id")
        except Exception as e:
            logger.error(f"Failed to post review summary: {e}")
            return None

    async def set_commit_status(
        self,
        repo_full_name: str,
        sha: str,
        state: str,
        description: str,
        installation_id: int | None = None,
        target_url: str | None = None,
    ) -> None:
        """Set a commit status check on a specific commit.

        Args:
            state: One of "pending", "success", "failure", "error".
            description: Short text shown on the PR (max 140 chars).
        """
        try:
            json_data = {
                "state": state,
                "description": description[:140],
                "context": "Argus — Code Review",
            }
            if target_url:
                json_data["target_url"] = target_url
            await self._make_api_request(
                "POST",
                f"/repos/{repo_full_name}/statuses/{sha}",
                installation_id=installation_id or 0,
                json_data=json_data,
            )
            logger.info(f"Set commit status {state} on {repo_full_name}@{sha[:8]}")
        except Exception as e:
            logger.error(f"Failed to set commit status: {e}")

    async def find_bot_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        installation_id: int | None = None,
    ) -> int | None:
        """Find an existing Argus summary comment on a PR to edit on re-push."""
        try:
            comments = await self._make_api_request(
                "GET",
                f"/repos/{repo_full_name}/issues/{pr_number}/comments",
                installation_id=installation_id or 0,
            )
            for comment in comments:
                body = comment.get("body", "")
                if "<!-- argus-review-summary -->" in body:
                    return comment["id"]
        except Exception as e:
            logger.warning(f"Failed to search for bot comment: {e}")
        return None

    async def edit_comment(
        self,
        repo_full_name: str,
        comment_id: int,
        body: str,
        installation_id: int | None = None,
    ) -> None:
        """Edit an existing issue/PR comment."""
        try:
            await self._make_api_request(
                "PATCH",
                f"/repos/{repo_full_name}/issues/comments/{comment_id}",
                installation_id=installation_id or 0,
                json_data={"body": body},
            )
        except Exception as e:
            logger.error(f"Failed to edit comment {comment_id}: {e}")

    async def post_issue_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        body: str,
        installation_id: int | None = None,
    ) -> int | None:
        """Post a comment on a PR (issue comment, not review comment)."""
        try:
            data = await self._make_api_request(
                "POST",
                f"/repos/{repo_full_name}/issues/{pr_number}/comments",
                installation_id=installation_id or 0,
                json_data={"body": body},
            )
            return data.get("id")
        except Exception as e:
            logger.error(f"Failed to post issue comment: {e}")
            return None

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify GitHub webhook HMAC-SHA256 signature."""
        if not signature.startswith("sha256="):
            return False

        expected = hmac.new(
            self.settings.github_webhook_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        received = signature.removeprefix("sha256=")
        return hmac.compare_digest(expected, received)
