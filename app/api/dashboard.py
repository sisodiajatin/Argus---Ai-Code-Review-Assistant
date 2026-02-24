"""Dashboard REST API endpoints."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, delete

from app.config import get_settings
from app.models.database import get_db
from app.models.repository import Repository
from app.models.pull_request import PullRequest, PRStatus
from app.models.review import ReviewFinding, ReviewSummary
from app.models.dashboard_schemas import (
    DashboardStats,
    RepoListItem,
    PRReviewListItem,
    ReviewDetail,
    FindingItem,
    TrendDataPoint,
    CategoryBreakdown,
    SeverityBreakdown,
    SettingsResponse,
    IgnoredPathsUpdate,
    ReReviewResponse,
    FeedbackRequest,
    FeedbackResponse,
    FeedbackStats,
    FeedbackCategoryRate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get overall dashboard statistics."""
    # Total repos
    repo_count = await db.scalar(select(func.count(Repository.id)))

    # Total PRs reviewed
    pr_count = await db.scalar(
        select(func.count(PullRequest.id)).where(PullRequest.status == "completed")
    )

    # Total findings
    findings_count = await db.scalar(select(func.count(ReviewFinding.id)))

    # Critical findings
    critical_count = await db.scalar(
        select(func.count(ReviewFinding.id)).where(ReviewFinding.severity == "critical")
    )

    # Average processing time
    avg_time = await db.scalar(select(func.avg(ReviewSummary.processing_time_ms)))

    # Total tokens
    total_tokens = await db.scalar(select(func.sum(ReviewSummary.tokens_used)))

    return DashboardStats(
        total_repos=repo_count or 0,
        total_prs_reviewed=pr_count or 0,
        total_findings=findings_count or 0,
        critical_findings=critical_count or 0,
        avg_processing_time_ms=round(avg_time or 0, 1),
        total_tokens_used=total_tokens or 0,
    )


@router.get("/dashboard/repos", response_model=list[RepoListItem])
async def list_repos(db: AsyncSession = Depends(get_db)):
    """List all connected repositories."""
    result = await db.execute(
        select(Repository).order_by(desc(Repository.updated_at))
    )
    repos = result.scalars().all()

    items = []
    for repo in repos:
        pr_count = await db.scalar(
            select(func.count(PullRequest.id)).where(PullRequest.repo_id == repo.id)
        )
        last_pr = await db.scalar(
            select(func.max(PullRequest.created_at)).where(PullRequest.repo_id == repo.id)
        )
        items.append(RepoListItem(
            id=repo.id,
            full_name=repo.full_name,
            owner=repo.owner,
            name=repo.name,
            is_active=bool(repo.is_active),
            pr_count=pr_count or 0,
            last_review=last_pr.isoformat() if last_pr else None,
        ))
    return items


@router.get("/dashboard/repos/{repo_id}/reviews", response_model=list[PRReviewListItem])
async def list_repo_reviews(repo_id: int, db: AsyncSession = Depends(get_db)):
    """List reviews for a specific repository."""
    result = await db.execute(
        select(PullRequest)
        .where(PullRequest.repo_id == repo_id)
        .order_by(desc(PullRequest.created_at))
        .limit(50)
    )
    prs = result.scalars().all()

    items = []
    for pr in prs:
        findings_count = await db.scalar(
            select(func.count(ReviewFinding.id)).where(ReviewFinding.pr_id == pr.id)
        )
        critical_count = await db.scalar(
            select(func.count(ReviewFinding.id)).where(
                ReviewFinding.pr_id == pr.id, ReviewFinding.severity == "critical"
            )
        )
        items.append(PRReviewListItem(
            id=pr.id,
            pr_number=pr.pr_number,
            title=pr.title,
            author=pr.author,
            status=pr.status,
            findings_count=findings_count or 0,
            critical_count=critical_count or 0,
            created_at=pr.created_at.isoformat() if pr.created_at else None,
            completed_at=pr.completed_at.isoformat() if pr.completed_at else None,
        ))
    return items


@router.get("/dashboard/reviews/{pr_id}", response_model=ReviewDetail)
async def get_review_detail(pr_id: int, db: AsyncSession = Depends(get_db)):
    """Get detailed review for a specific PR."""
    result = await db.execute(select(PullRequest).where(PullRequest.id == pr_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="Review not found")

    # Get findings
    findings_result = await db.execute(
        select(ReviewFinding).where(ReviewFinding.pr_id == pr_id)
    )
    findings = findings_result.scalars().all()

    # Get summary
    summary_result = await db.execute(
        select(ReviewSummary).where(ReviewSummary.pr_id == pr_id)
    )
    summary = summary_result.scalar_one_or_none()

    findings_count = len(findings)
    critical_count = sum(1 for f in findings if f.severity == "critical")

    return ReviewDetail(
        pr=PRReviewListItem(
            id=pr.id,
            pr_number=pr.pr_number,
            title=pr.title,
            author=pr.author,
            status=pr.status,
            findings_count=findings_count,
            critical_count=critical_count,
            created_at=pr.created_at.isoformat() if pr.created_at else None,
            completed_at=pr.completed_at.isoformat() if pr.completed_at else None,
        ),
        findings=[
            FindingItem(
                id=f.id,
                file_path=f.file_path,
                line_start=f.line_start,
                line_end=f.line_end,
                category=f.category,
                severity=f.severity,
                title=f.title,
                description=f.description,
                suggested_fix=f.suggested_fix,
                feedback=f.feedback,
                feedback_note=f.feedback_note,
            )
            for f in findings
        ],
        summary_text=summary.summary_text if summary else None,
        overall_assessment=summary.overall_assessment if summary else None,
        model_used=summary.model_used if summary else None,
        tokens_used=summary.tokens_used if summary else 0,
        processing_time_ms=summary.processing_time_ms if summary else 0,
    )


@router.post("/dashboard/reviews/{pr_id}/re-review", response_model=ReReviewResponse)
async def re_review(pr_id: int, db: AsyncSession = Depends(get_db)):
    """Re-run a review for a GitHub PR. Only works for webhook-based reviews."""
    result = await db.execute(select(PullRequest).where(PullRequest.id == pr_id))
    pr = result.scalar_one_or_none()
    if not pr:
        raise HTTPException(status_code=404, detail="Review not found")

    # Get the repo to check for installation_id
    repo_result = await db.execute(select(Repository).where(Repository.id == pr.repo_id))
    repo = repo_result.scalar_one_or_none()
    if not repo or not repo.installation_id:
        raise HTTPException(
            status_code=400,
            detail="Re-review is only available for GitHub webhook-based reviews",
        )

    if pr.status == PRStatus.REVIEWING.value:
        return ReReviewResponse(status="already_running", message="A review is already in progress")

    # Clear old findings and summary
    await db.execute(delete(ReviewFinding).where(ReviewFinding.pr_id == pr_id))
    await db.execute(delete(ReviewSummary).where(ReviewSummary.pr_id == pr_id))

    # Reset PR status
    pr.status = PRStatus.PENDING.value
    pr.completed_at = None
    await db.commit()

    # Trigger the review pipeline asynchronously
    from app.api.webhooks import _run_review_pipeline
    settings = get_settings()

    asyncio.create_task(
        _run_review_pipeline(
            db_url=settings.database_url,
            repo_full_name=repo.full_name,
            pr_number=pr.pr_number,
            pr_record_id=pr.id,
            repo_id=repo.id,
            installation_id=repo.installation_id,
            pr_title=pr.title or "",
            pr_author=pr.author or "",
            head_sha=pr.head_sha or "",
            base_branch=pr.base_branch or "main",
            ignored_paths=repo.ignored_paths,
        )
    )

    return ReReviewResponse(status="processing", message="Re-review started")


@router.get("/dashboard/settings", response_model=SettingsResponse)
async def get_dashboard_settings():
    """Get current server settings (safe fields only — no secrets)."""
    settings = get_settings()
    return SettingsResponse(
        ai_model=settings.ai_model,
        ai_base_url=settings.ai_base_url,
        app_host=settings.app_host,
        app_port=settings.app_port,
        webhook_url=f"http://{settings.app_host}:{settings.app_port}/api/webhooks/github",
        max_files_per_review=settings.max_files_per_review,
        chunk_token_limit=settings.chunk_token_limit,
    )


@router.get("/dashboard/analytics/trends", response_model=list[TrendDataPoint])
async def get_trends(days: int = 30, db: AsyncSession = Depends(get_db)):
    """Get review trends over the last N days."""
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(PullRequest)
        .where(PullRequest.created_at >= start_date)
        .order_by(PullRequest.created_at)
    )
    prs = result.scalars().all()

    # Group by date
    daily: dict[str, dict] = {}
    for pr in prs:
        date_str = pr.created_at.strftime("%Y-%m-%d") if pr.created_at else "unknown"
        if date_str not in daily:
            daily[date_str] = {"reviews": 0, "findings": 0}
        daily[date_str]["reviews"] += 1

        findings_count = await db.scalar(
            select(func.count(ReviewFinding.id)).where(ReviewFinding.pr_id == pr.id)
        )
        daily[date_str]["findings"] += findings_count or 0

    return [
        TrendDataPoint(date=date, reviews=data["reviews"], findings=data["findings"])
        for date, data in sorted(daily.items())
    ]


@router.get("/dashboard/analytics/categories", response_model=list[CategoryBreakdown])
async def get_category_breakdown(db: AsyncSession = Depends(get_db)):
    """Get findings breakdown by category."""
    result = await db.execute(
        select(ReviewFinding.category, func.count(ReviewFinding.id))
        .group_by(ReviewFinding.category)
    )
    return [
        CategoryBreakdown(category=row[0], count=row[1])
        for row in result.all()
    ]


@router.get("/dashboard/analytics/severity", response_model=list[SeverityBreakdown])
async def get_severity_breakdown(db: AsyncSession = Depends(get_db)):
    """Get findings breakdown by severity."""
    result = await db.execute(
        select(ReviewFinding.severity, func.count(ReviewFinding.id))
        .group_by(ReviewFinding.severity)
    )
    return [
        SeverityBreakdown(severity=row[0], count=row[1])
        for row in result.all()
    ]


# --- Finding Feedback ---

@router.post("/dashboard/findings/{finding_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    finding_id: int,
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit feedback (helpful / not_helpful) on a specific finding."""
    if body.feedback not in ("helpful", "not_helpful"):
        raise HTTPException(status_code=400, detail="feedback must be 'helpful' or 'not_helpful'")

    result = await db.execute(
        select(ReviewFinding).where(ReviewFinding.id == finding_id)
    )
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    finding.feedback = body.feedback
    finding.feedback_note = body.note
    finding.feedback_at = datetime.now(timezone.utc)
    await db.commit()

    return FeedbackResponse(
        id=finding_id,
        feedback=body.feedback,
        message="Feedback recorded",
    )


@router.get("/dashboard/analytics/feedback", response_model=FeedbackStats)
async def get_feedback_stats(db: AsyncSession = Depends(get_db)):
    """Get aggregate feedback statistics across all findings."""
    total_rated = await db.scalar(
        select(func.count(ReviewFinding.id)).where(ReviewFinding.feedback.isnot(None))
    ) or 0

    helpful_count = await db.scalar(
        select(func.count(ReviewFinding.id)).where(ReviewFinding.feedback == "helpful")
    ) or 0

    not_helpful_count = await db.scalar(
        select(func.count(ReviewFinding.id)).where(ReviewFinding.feedback == "not_helpful")
    ) or 0

    helpful_rate = (helpful_count / total_rated * 100) if total_rated > 0 else 0.0

    # Per-category breakdown
    rows = (await db.execute(
        select(
            ReviewFinding.category,
            func.count(ReviewFinding.id),
            func.sum(func.iif(ReviewFinding.feedback == "helpful", 1, 0)),
        )
        .where(ReviewFinding.feedback.isnot(None))
        .group_by(ReviewFinding.category)
    )).all()

    by_category = []
    for cat, total, helpful in rows:
        rate = (helpful / total * 100) if total > 0 else 0.0
        by_category.append(FeedbackCategoryRate(
            category=cat, total=total, helpful=helpful or 0, rate=round(rate, 1),
        ))

    return FeedbackStats(
        total_rated=total_rated,
        helpful_count=helpful_count,
        not_helpful_count=not_helpful_count,
        helpful_rate=round(helpful_rate, 1),
        by_category=by_category,
    )
