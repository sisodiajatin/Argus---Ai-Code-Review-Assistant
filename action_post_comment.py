"""Post Argus review results as a PR comment via GitHub API.

Used by the GitHub Action to post findings after running argus review.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

MARKER = "<!-- argus-review-summary -->"
API = "https://api.github.com"


def main():
    if len(sys.argv) < 4:
        print("Usage: action_post_comment.py <owner/repo> <pr_number> <results.json>")
        sys.exit(1)

    repo = sys.argv[1]
    pr_number = sys.argv[2]
    results_file = sys.argv[3]
    token = os.environ.get("GITHUB_TOKEN", "")

    if not token:
        print("Warning: No GITHUB_TOKEN, skipping PR comment")
        return

    # Load results
    try:
        with open(results_file, "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("No review results found, skipping comment")
        return

    findings = data.get("findings", [])
    summary = data.get("summary", "")
    pr_description = data.get("pr_description", "")

    # Count severities
    critical = sum(1 for f in findings if f.get("severity") == "critical")
    warnings = sum(1 for f in findings if f.get("severity") == "warning")
    suggestions = sum(1 for f in findings if f.get("severity") == "suggestion")

    # Build comment body
    parts = [MARKER]
    parts.append("## 👁️ Argus Code Review")
    parts.append("")

    # PR auto-summary
    if pr_description:
        parts.append("### PR Summary")
        parts.append("")
        parts.append(pr_description)
        parts.append("")

    if critical > 0:
        parts.append(f"**Status:** 🔴 **{critical} critical issue{'s' if critical != 1 else ''} found**")
    elif warnings > 0:
        parts.append(f"**Status:** 🟡 **Minor issues found**")
    elif findings:
        parts.append(f"**Status:** 🟢 **Suggestions only — looking good!**")
    else:
        parts.append(f"**Status:** ✅ **No issues found — great job!**")

    parts.append("")

    if findings:
        parts.append("| Severity | Count |")
        parts.append("|----------|-------|")
        if critical:
            parts.append(f"| 🔴 Critical | {critical} |")
        if warnings:
            parts.append(f"| 🟡 Warning | {warnings} |")
        if suggestions:
            parts.append(f"| 🟢 Suggestion | {suggestions} |")
        parts.append("")

    # Top findings
    severity_map = {"🔴": "critical", "🟡": "warning", "🟢": "suggestion"}
    emoji_map = {"critical": "🔴", "warning": "🟡", "suggestion": "🟢"}
    top = [f for f in findings if f.get("severity") in ("critical", "warning")][:5]
    if top:
        parts.append("### Top Findings")
        parts.append("")
        for f in top:
            emoji = emoji_map.get(f.get("severity", ""), "ℹ️")
            parts.append(f"- {emoji} **{f.get('title', 'Issue')}** — `{f.get('file_path', '?')}`")
        parts.append("")

    if summary:
        parts.append("### Summary")
        parts.append("")
        parts.append(summary)
        parts.append("")

    parts.append("---")
    parts.append("*Powered by [Argus](https://github.com/sisodiajatin/Argus---Ai-Code-Review-Assistant) — GitHub Action*")

    body = "\n".join(parts)

    # Check for existing Argus comment to edit
    try:
        comment_id = find_existing_comment(repo, pr_number, token)
        if comment_id:
            edit_comment(repo, comment_id, body, token)
            print(f"Updated existing Argus comment #{comment_id}")
        else:
            post_comment(repo, pr_number, body, token)
            print(f"Posted Argus review comment on PR #{pr_number}")
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            print(
                "::warning::Could not post the Argus comment (HTTP "
                f"{e.code}). Give the workflow 'permissions: pull-requests: write'. "
                "PRs from forks get a read-only token."
            )
        else:
            print(f"::warning::Could not post the Argus comment: HTTP {e.code} {e.reason}")
    # Failing the job on critical findings is the action's 'fail_on_critical' step.


def _request(url, token, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return urllib.request.urlopen(req, timeout=30)


def _next_link(link_header):
    """Return the rel="next" URL from a GitHub Link header, if any."""
    match = re.search(r'<([^>]+)>;\s*rel="next"', link_header or "")
    return match.group(1) if match else None


def find_existing_comment(repo, pr_number, token):
    """Find our summary comment, walking every page of PR comments."""
    url = f"{API}/repos/{repo}/issues/{pr_number}/comments?per_page=100"
    while url:
        with _request(url, token) as resp:
            for c in json.loads(resp.read()):
                if MARKER in (c.get("body") or ""):
                    return c["id"]
            url = _next_link(resp.headers.get("Link"))
    return None


def edit_comment(repo, comment_id, body, token):
    _request(f"{API}/repos/{repo}/issues/comments/{comment_id}", token, "PATCH", {"body": body}).close()


def post_comment(repo, pr_number, body, token):
    _request(f"{API}/repos/{repo}/issues/{pr_number}/comments", token, "POST", {"body": body}).close()


if __name__ == "__main__":
    main()
