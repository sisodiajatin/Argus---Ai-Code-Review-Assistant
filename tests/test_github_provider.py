"""Tests for GitHub API pagination, token caching and batched reviews."""

import re
import time

import pytest

from app.services.vcs import github_provider as gp
from app.services.vcs.github_provider import GitHubProvider

INSTALLATION = 7


@pytest.fixture(autouse=True)
def cached_token():
    """Pretend we already hold a valid installation token (skips JWT signing)."""
    gp._installation_tokens[INSTALLATION] = ("tok", time.time() + 3600)
    yield
    gp._installation_tokens.clear()


def _file(i):
    return {"filename": f"src/f{i}.py", "status": "modified", "additions": 1,
            "deletions": 0, "patch": "@@ -1 +1 @@\n-a\n+b"}


async def test_pr_files_follow_every_page(httpx_mock):
    base = "https://api.github.com/repos/o/r/pulls/5/files"
    httpx_mock.add_response(
        url=f"{base}?per_page=100",
        json=[_file(i) for i in range(100)],
        headers={"Link": f'<{base}?per_page=100&page=2>; rel="next"'},
    )
    httpx_mock.add_response(
        url=f"{base}?per_page=100&page=2",
        json=[_file(i) for i in range(100, 135)],
    )

    files = await GitHubProvider().get_pr_files("o/r", 5, INSTALLATION)

    assert len(files) == 135
    assert files[-1].filename == "src/f134.py"


async def test_bot_comment_found_beyond_first_page(httpx_mock):
    base = "https://api.github.com/repos/o/r/issues/5/comments"
    httpx_mock.add_response(
        url=f"{base}?per_page=100",
        json=[{"id": i, "body": "lgtm"} for i in range(100)],
        headers={"Link": f'<{base}?per_page=100&page=2>; rel="next"'},
    )
    httpx_mock.add_response(
        url=f"{base}?per_page=100&page=2",
        json=[{"id": 999, "body": f"{gp.SUMMARY_MARKER}\nsummary"}],
    )

    assert await GitHubProvider().find_bot_comment("o/r", 5, INSTALLATION) == 999


async def test_installation_token_shared_across_instances(httpx_mock, monkeypatch):
    gp._installation_tokens.clear()
    monkeypatch.setattr(gp.jwt, "encode", lambda *a, **k: "jwt")
    monkeypatch.setattr(GitHubProvider, "_read_private_key", lambda self: "key")
    httpx_mock.add_response(
        method="POST",
        url=f"https://api.github.com/app/installations/{INSTALLATION}/access_tokens",
        json={"token": "fresh", "expires_at": "2099-01-01T00:00:00Z"},
    )

    first = await GitHubProvider()._get_installation_token(INSTALLATION)
    second = await GitHubProvider()._get_installation_token(INSTALLATION)

    assert first == second == "fresh"
    assert len(httpx_mock.get_requests()) == 1  # second call used the cache


async def test_create_review_sends_one_request_with_all_comments(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://api.github.com/repos/o/r/pulls/5/reviews",
        json={"id": 42},
    )
    comments = [
        {"path": "a.py", "line": 2, "side": "RIGHT", "body": "x"},
        {"path": "b.py", "line": 9, "side": "RIGHT", "body": "y"},
    ]

    review_id = await GitHubProvider().create_review("o/r", 5, "sha", comments, installation_id=INSTALLATION)

    assert review_id == 42
    sent = httpx_mock.get_requests()[0]
    import json
    payload = json.loads(sent.content)
    assert payload["commit_id"] == "sha"
    assert payload["event"] == "COMMENT"
    assert len(payload["comments"]) == 2
    assert re.match(r"token tok", sent.headers["Authorization"])
