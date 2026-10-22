"""Tests for the GitHub Action's PR comment script."""

import io
import json
import sys
import urllib.error
from unittest.mock import patch

import action_post_comment as apc


class FakeResponse(io.BytesIO):
    def __init__(self, data, link=None):
        super().__init__(json.dumps(data).encode())
        self.headers = {"Link": link} if link else {}


def test_finds_existing_comment_on_a_later_page():
    pages = {
        "https://api.github.com/repos/o/r/issues/1/comments?per_page=100": FakeResponse(
            [{"id": i, "body": "unrelated"} for i in range(100)],
            link='<https://api.github.com/page2>; rel="next"',
        ),
        "https://api.github.com/page2": FakeResponse(
            [{"id": 555, "body": f"{apc.MARKER}\n## Argus"}]
        ),
    }
    with patch.object(apc.urllib.request, "urlopen", side_effect=lambda req, timeout=30: pages[req.full_url]):
        assert apc.find_existing_comment("o/r", 1, "t") == 555


def test_missing_permission_warns_instead_of_crashing(tmp_path, capsys, monkeypatch):
    results = tmp_path / "r.json"
    results.write_text(json.dumps({"findings": [], "summary": "s"}))
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(sys, "argv", ["x", "o/r", "1", str(results)])

    def forbidden(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    with patch.object(apc.urllib.request, "urlopen", side_effect=forbidden):
        apc.main()  # must not raise or sys.exit

    assert "pull-requests: write" in capsys.readouterr().out


def test_critical_findings_do_not_exit_from_comment_script(tmp_path, monkeypatch):
    """Failing the job is the action's fail_on_critical step, not this script."""
    results = tmp_path / "r.json"
    results.write_text(json.dumps({"findings": [
        {"severity": "critical", "title": "x", "file_path": "a.py"}
    ]}))
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setattr(sys, "argv", ["x", "o/r", "1", str(results)])
    with patch.object(apc, "find_existing_comment", return_value=None), \
         patch.object(apc, "post_comment") as post:
        apc.main()
    assert apc.MARKER in post.call_args.args[2]
