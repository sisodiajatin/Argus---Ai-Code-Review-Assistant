"""Review-specific prompt templates for code analysis."""

REVIEW_PROMPT_TEMPLATE = """Review the following code changes from a pull request.

## PR Context
{pr_context}

## Code Changes
{diff_content}

## Instructions
Analyze the code changes above and provide your findings. For each issue found, provide:
1. The exact file path
2. The line number (from the new version of the file)
3. A category (bug, security, performance, style, architecture)
4. A severity level (critical, warning, suggestion)
5. A clear, concise title
6. A detailed description explaining WHY this is an issue
7. A suggested fix (code snippet if applicable)

If the code looks good and you have no significant findings, say so briefly.

Respond in the following JSON format:
```json
{{
  "findings": [
    {{
      "file_path": "path/to/file.py",
      "line_start": 42,
      "line_end": 42,
      "category": "security",
      "severity": "critical",
      "title": "Hardcoded API key in source code",
      "description": "The API key is hardcoded directly in the source file. This exposes the credential in version control and makes rotation difficult.",
      "suggested_fix": "Move the API key to an environment variable:\\n```python\\napi_key = os.environ['API_KEY']\\n```"
    }}
  ],
  "summary": "Brief overall assessment of the changes"
}}
```

Important: Return ONLY valid JSON. No additional text before or after the JSON block.
"""


SUMMARY_PROMPT_TEMPLATE = """Based on the following individual review findings from a pull request, generate a concise summary review.

## PR Information
- **Title**: {pr_title}
- **Author**: {pr_author}
- **Files Changed**: {files_changed}
- **Total Additions**: +{additions}
- **Total Deletions**: -{deletions}

## Individual Findings
{findings_text}

## Instructions
Generate a summary that includes:
1. A brief overall assessment (1-2 sentences)
2. The most critical issues that must be addressed
3. Key suggestions for improvement
4. Any positive aspects of the code changes

Format the summary in markdown, suitable for posting as a GitHub PR review comment.
Start with a header and use emoji indicators for severity:
- 🔴 Critical issues
- 🟡 Warnings
- 🟢 Suggestions
- ✅ Positive observations

Keep it concise but comprehensive. Developers should be able to scan this quickly.
"""


PR_SUMMARY_PROMPT_TEMPLATE = """Summarize the following code changes in plain English. This summary will be posted as the first comment on a pull request so that reviewers and team members can quickly understand **what** the PR does without reading every diff.

## PR Context
- **Title**: {pr_title}
- **Author**: {pr_author}
- **Target Branch**: {base_branch}
- **Files Changed**: {files_changed}
- **Additions**: +{additions}  |  **Deletions**: -{deletions}

## Changed Files
{file_list}

## Code Changes (abbreviated)
{diff_content}

## Instructions
Write a concise PR summary using this structure:

1. **What this PR does** — 1-3 sentences describing the overall change in plain language.
2. **Key changes** — A bulleted list of the most important things that changed (max 8 bullets). Group by feature or area, not by file.
3. **Notable decisions** — If you spot interesting design choices, trade-offs, or migration patterns, mention them briefly (1-2 sentences). Skip this section if nothing stands out.

Guidelines:
- Write for a developer who has NOT looked at the code yet.
- Use concrete language: "Adds a retry mechanism to the HTTP client" not "Modifies network code".
- Do NOT list review findings or bugs — this is a neutral description, not a review.
- Keep the entire summary under 250 words.
- Format in markdown.
"""


def build_review_prompt(
    pr_title: str,
    pr_author: str,
    diff_content: str,
    base_branch: str = "main",
) -> str:
    """Build the review prompt for a code chunk.

    Args:
        pr_title: The pull request title.
        pr_author: The PR author's username.
        diff_content: Formatted diff content for this chunk.
        base_branch: The target branch name.

    Returns:
        Formatted prompt string ready for the LLM.
    """
    pr_context = (
        f"**Title**: {pr_title}\n"
        f"**Author**: {pr_author}\n"
        f"**Target Branch**: {base_branch}"
    )
    return REVIEW_PROMPT_TEMPLATE.format(
        pr_context=pr_context,
        diff_content=diff_content,
    )


def build_summary_prompt(
    pr_title: str,
    pr_author: str,
    files_changed: int,
    additions: int,
    deletions: int,
    findings_text: str,
) -> str:
    """Build the summary prompt for generating the final review summary.

    Args:
        pr_title: The pull request title.
        pr_author: The PR author's username.
        files_changed: Number of files changed.
        additions: Total lines added.
        deletions: Total lines deleted.
        findings_text: Formatted text of all individual findings.

    Returns:
        Formatted summary prompt string.
    """
    return SUMMARY_PROMPT_TEMPLATE.format(
        pr_title=pr_title,
        pr_author=pr_author,
        files_changed=files_changed,
        additions=additions,
        deletions=deletions,
        findings_text=findings_text,
    )


def build_pr_summary_prompt(
    pr_title: str,
    pr_author: str,
    base_branch: str,
    files_changed: int,
    additions: int,
    deletions: int,
    file_list: str,
    diff_content: str,
) -> str:
    """Build the prompt for generating a plain-English PR summary.

    Args:
        pr_title: The pull request title.
        pr_author: The PR author's username.
        base_branch: Target branch name.
        files_changed: Number of files changed.
        additions: Total lines added.
        deletions: Total lines deleted.
        file_list: Bullet list of changed file paths.
        diff_content: Abbreviated diff content.

    Returns:
        Formatted prompt string.
    """
    return PR_SUMMARY_PROMPT_TEMPLATE.format(
        pr_title=pr_title,
        pr_author=pr_author,
        base_branch=base_branch,
        files_changed=files_changed,
        additions=additions,
        deletions=deletions,
        file_list=file_list,
        diff_content=diff_content,
    )
