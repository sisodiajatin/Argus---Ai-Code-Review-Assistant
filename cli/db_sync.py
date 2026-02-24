"""Save CLI review results to the dashboard database.

Bridges the CLI review output with the SQLAlchemy models so that
results appear in the React dashboard.
"""

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import init_db, get_session_factory, close_db
from app.models.repository import Repository
from app.models.pull_request import PullRequest, PRStatus
from app.models.review import ReviewFinding, ReviewSummary
from app.services.review_pipeline import ReviewResult


async def save_review_to_db(
    result: ReviewResult,
    repo_info: dict,
    title: str,
    change_type: str,
) -> None:
    """Save a CLI review result into the dashboard database.

    Creates or updates the repository, creates a pseudo-PR entry
    for the local review, and stores all findings + summary.
    """
    await init_db()
    factory = get_session_factory()

    async with factory() as session:
        try:
            # 1) Find or create the repository
            repo = await _get_or_create_repo(session, repo_info)

            # 2) Create a PR record for this CLI review
            pr = PullRequest(
                repo_id=repo.id,
                pr_number=_generate_cli_pr_number(repo_info, change_type),
                title=title,
                author=repo_info.get("author", "local"),
                head_sha=repo_info.get("head_sha", "0" * 40),
                base_sha=None,
                head_branch=repo_info.get("branch", "unknown"),
                base_branch="main",
                status=PRStatus.COMPLETED.value,
                completed_at=datetime.now(timezone.utc),
            )
            session.add(pr)
            await session.flush()  # get pr.id

            # 3) Save findings
            for f in result.findings:
                finding = ReviewFinding(
                    pr_id=pr.id,
                    file_path=f.file_path,
                    line_start=f.line_start,
                    line_end=f.line_end,
                    category=f.category,
                    severity=f.severity,
                    title=f.title,
                    description=f.description,
                    suggested_fix=f.suggested_fix,
                )
                session.add(finding)

            # 4) Save review summary
            critical = sum(1 for f in result.findings if f.severity == "critical")
            warnings = sum(1 for f in result.findings if f.severity == "warning")
            suggestions = sum(1 for f in result.findings if f.severity == "suggestion")

            assessment = "approved"
            if critical > 0:
                assessment = "needs_changes"
            elif warnings > 0:
                assessment = "minor_issues"

            summary = ReviewSummary(
                pr_id=pr.id,
                total_findings=len(result.findings),
                critical_count=critical,
                warning_count=warnings,
                suggestion_count=suggestions,
                overall_assessment=assessment,
                summary_text=result.summary or f"CLI review: {len(result.findings)} findings",
                tokens_used=result.tokens_used,
                model_used=result.model_used,
                processing_time_ms=result.processing_time_ms,
                chunks_processed=result.chunks_processed,
            )
            session.add(summary)

            await session.commit()

        except Exception:
            await session.rollback()
            raise
        finally:
            await close_db()


async def _get_or_create_repo(session: AsyncSession, repo_info: dict) -> Repository:
    """Find existing repo by name or create a new one."""
    remote = repo_info.get("remote", "local/unknown")
    # Extract owner/name from remote URL or use as-is
    full_name = _parse_repo_name(remote)
    parts = full_name.split("/")
    owner = parts[0] if len(parts) >= 2 else "local"
    name = parts[1] if len(parts) >= 2 else full_name

    # Look up by full_name
    result = await session.execute(
        select(Repository).where(Repository.full_name == full_name)
    )
    repo = result.scalar_one_or_none()

    if repo is None:
        # Generate a stable github_id from the full_name
        github_id = int(hashlib.md5(full_name.encode()).hexdigest()[:8], 16)
        repo = Repository(
            github_id=github_id,
            full_name=full_name,
            owner=owner,
            name=name,
            is_active=1,
        )
        session.add(repo)
        await session.flush()

    return repo


def _parse_repo_name(remote: str) -> str:
    """Extract 'owner/repo' from a git remote URL."""
    # Handle SSH: git@github.com:owner/repo.git
    if ":" in remote and "@" in remote:
        path = remote.split(":")[-1]
        return path.replace(".git", "")
    # Handle HTTPS: https://github.com/owner/repo.git
    if "/" in remote:
        parts = remote.rstrip("/").split("/")
        if len(parts) >= 2:
            name = parts[-1].replace(".git", "")
            owner = parts[-2]
            return f"{owner}/{name}"
    return remote


def _generate_cli_pr_number(repo_info: dict, change_type: str) -> int:
    """Generate a unique PR number for CLI reviews.

    Uses a hash of the timestamp + branch to avoid collisions.
    CLI reviews use negative PR numbers to distinguish from real PRs.
    """
    now = datetime.now(timezone.utc)
    key = f"{repo_info.get('branch', '')}-{change_type}-{now.isoformat()}"
    return int(hashlib.md5(key.encode()).hexdigest()[:6], 16)
