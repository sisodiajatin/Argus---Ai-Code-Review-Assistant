"""Incremental review: on a new push, only re-review files that changed.

Granularity is per FILE, not per line, on purpose. If only the new lines
were reviewed, the commit status would reflect only those lines: a PR with
an unfixed critical from an earlier push would go green on the next push.
Instead:

- files changed since the last completed review are re-reviewed in full
  (their whole PR diff), so their old findings are replaced and a fix clears
  its finding;
- files untouched since then are not sent to the model; their previous
  findings are carried forward unchanged (same content, same line numbers).

The status check therefore always covers the whole PR.

Falls back to a full review (returns None) when there is no earlier
completed review, the history was rewritten (force-push/rebase), the compare
is too large to trust, or anything goes wrong.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PullRequest, PRStatus
from app.models.review import ReviewFinding, ReviewSummary
from app.models.schemas import AIFinding
from app.services.vcs.base import PRFile

logger = logging.getLogger(__name__)

# GitHub's compare API lists at most 300 files; at that size, don't trust it.
MAX_COMPARE_FILES = 300


@dataclass
class IncrementalPlan:
    """What to re-review and what to carry over from the previous review."""

    base_sha: str                      # head of the previous completed review
    review_files: list[PRFile]         # files to send to the model
    carried_findings: list[AIFinding]  # findings kept from untouched files
    total_files: int                   # files in the whole PR
    previous_summary: str = ""
    unchanged_files: list[str] = field(default_factory=list)

    @property
    def describe(self) -> str:
        """One-line note for the PR summary comment."""
        return (
            f"Incremental review: re-reviewed {len(self.review_files)} of {self.total_files} "
            f"file{'s' if self.total_files != 1 else ''} changed since `{self.base_sha[:7]}`; "
            f"{len(self.carried_findings)} finding"
            f"{'s' if len(self.carried_findings) != 1 else ''} carried over from unchanged files."
        )


def _to_ai_finding(row: ReviewFinding) -> AIFinding:
    return AIFinding(
        file_path=row.file_path,
        line_start=row.line_start,
        line_end=row.line_end,
        category=row.category,
        severity=row.severity,
        title=row.title,
        description=row.description,
        suggested_fix=row.suggested_fix,
    )


async def find_previous_review(
    db: AsyncSession, repo_id: int, pr_number: int, head_sha: str
) -> PullRequest | None:
    """Most recent completed review of an earlier commit of the same PR."""
    return (
        await db.execute(
            select(PullRequest)
            .join(ReviewSummary, ReviewSummary.pr_id == PullRequest.id)
            .where(
                PullRequest.repo_id == repo_id,
                PullRequest.pr_number == pr_number,
                PullRequest.head_sha != head_sha,
                PullRequest.status == PRStatus.COMPLETED.value,
            )
            .order_by(PullRequest.completed_at.desc(), PullRequest.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def plan_incremental_review(
    db: AsyncSession,
    github,
    *,
    repo_full_name: str,
    repo_id: int,
    pr_number: int,
    head_sha: str,
    pr_files: list[PRFile],
    installation_id: int | None,
) -> IncrementalPlan | None:
    """Return a plan for an incremental review, or None for a full review."""
    previous = await find_previous_review(db, repo_id, pr_number, head_sha)
    if previous is None or not previous.head_sha:
        return None

    try:
        status, changed_paths = await github.compare_commits(
            repo_full_name, previous.head_sha, head_sha, installation_id
        )
    except Exception as e:
        logger.warning(f"Compare {previous.head_sha[:7]}...{head_sha[:7]} failed ({e}); full review")
        return None

    if status != "ahead":
        # "diverged"/"behind": history was rewritten, "since last review" is undefined.
        logger.info(f"Compare status '{status}' for {repo_full_name}#{pr_number}; full review")
        return None
    if len(changed_paths) >= MAX_COMPARE_FILES:
        return None

    changed = set(changed_paths)
    review_files = [
        f for f in pr_files
        if f.filename in changed or (f.previous_filename and f.previous_filename in changed)
    ]
    unchanged = {f.filename for f in pr_files} - {f.filename for f in review_files}

    rows = (
        await db.execute(select(ReviewFinding).where(ReviewFinding.pr_id == previous.id))
    ).scalars().all()
    carried = [
        _to_ai_finding(r)
        for r in rows
        # Unchanged file, still in the PR, and not rejected by a reviewer.
        if r.file_path in unchanged and r.feedback != "not_helpful"
    ]

    summary = (
        await db.execute(select(ReviewSummary.summary_text).where(ReviewSummary.pr_id == previous.id))
    ).scalar_one_or_none()

    return IncrementalPlan(
        base_sha=previous.head_sha,
        review_files=review_files,
        carried_findings=carried,
        total_files=len(pr_files),
        previous_summary=summary or "",
        unchanged_files=sorted(unchanged),
    )
