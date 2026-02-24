"""Post Argus review results as a PR comment via GitHub API.

Used by the GitHub Action to post findings after running argus review.
"""

import json
import os
import sys
import urllib.request


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
    parts = ["<!-- argus-review-summary -->"]
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
    parts.append("*Powered by [Argus](https://github.com/sisodiajatin/argus) — GitHub Action*")

    body = "\n".join(parts)

    # Check for existing Argus comment to edit
    comment_id = find_existing_comment(repo, pr_number, token)

    if comment_id:
        edit_comment(repo, comment_id, body, token)
        print(f"Updated existing Argus comment #{comment_id}")
    else:
        post_comment(repo, pr_number, body, token)
        print(f"Posted Argus review comment on PR #{pr_number}")

    # Exit with failure if critical issues
    if critical > 0:
        sys.exit(1)


def find_existing_comment(repo, pr_number, token):
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            comments = json.loads(resp.read())
            for c in comments:
                if "<!-- argus-review-summary -->" in c.get("body", ""):
                    return c["id"]
    except Exception:
        pass
    return None


def edit_comment(repo, comment_id, body, token):
    url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}"
    data = json.dumps({"body": body}).encode()
    req = urllib.request.Request(url, data=data, method="PATCH", headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    urllib.request.urlopen(req)


def post_comment(repo, pr_number, body, token):
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    data = json.dumps({"body": body}).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    urllib.request.urlopen(req)


if __name__ == "__main__":
    main()
