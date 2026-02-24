"""GitHub webhook endpoint.

Receives webhook events from GitHub, validates their signatures,
and triggers the code review pipeline for pull request events.
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.database import get_db
from app.models.repository import Repository
from app.models.pull_request import PullRequest, PRStatus
from app.models.review import ReviewFinding, ReviewSummary, FindingCategory, FindingSeverity
from app.models.schemas import WebhookResponse
from app.services.vcs.github_provider import GitHubProvider
from app.services.review_pipeline import ReviewPipeline
from app.services.publisher import ReviewPublisher

logger = logging.getLogger(__name__)
router = APIRouter()

# PR events we care about
REVIEWABLE_ACTIONS = {"opened", "synchronize", "reopened"}


@router.post("/webhooks/github", response_model=WebhookResponse)
async def github_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle incoming GitHub webhook events.

    This endpoint:
    1. Validates the webhook signature
    2. Filters for relevant PR events
    3. Triggers the review pipeline asynchronously
    """
    settings = get_settings()
    github_provider = GitHubProvider()

    # Read raw body for signature verification
    body = await request.body()

    # Verify webhook signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not github_provider.verify_webhook_signature(body, signature):
        logger.warning("Invalid webhook signature received")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse the event
    event_type = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()

    logger.info(f"Received webhook: event={event_type}, action={payload.get('action')}")

    # We only care about pull request events
    if event_type != "pull_request":
        return WebhookResponse(
            status="ignored",
            message=f"Event type '{event_type}' is not handled",
        )

    action = payload.get("action", "")
    if action not in REVIEWABLE_ACTIONS:
        return WebhookResponse(
            status="ignored",
            message=f"PR action '{action}' is not reviewable",
        )

    # Extract PR info from payload
    pr_data = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})
    installation_data = payload.get("installation", {})

    pr_number = pr_data.get("number")
    repo_full_name = repo_data.get("full_name")
    installation_id = installation_data.get("id")

    if not pr_number or not repo_full_name:
        raise HTTPException(status_code=400, detail="Missing PR or repository data")

    # Ensure the repository exists in our database
    repo = await _get_or_create_repo(db, repo_data, installation_id)

    # Create or update the PR record
    pr_record = await _get_or_create_pr(db, repo, pr_data)

    head_sha = pr_data.get("head", {}).get("sha", "")

    # Set pending commit status check
    try:
        await github_provider.set_commit_status(
            repo_full_name=repo_full_name,
            sha=head_sha,
            state="pending",
            description="Argus is reviewing your code...",
            installation_id=installation_id,
        )
    except Exception as e:
        logger.warning(f"Failed to set pending status: {e}")

    # Trigger the review pipeline asynchronously
    asyncio.create_task(
        _run_review_pipeline(
            db_url=settings.database_url,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            pr_record_id=pr_record.id,
            repo_id=repo.id,
            installation_id=installation_id,
            pr_title=pr_data.get("title", ""),
            pr_author=pr_data.get("user", {}).get("login", ""),
            head_sha=head_sha,
            base_branch=pr_data.get("base", {}).get("ref", "main"),
            ignored_paths=repo.ignored_paths,
        )
    )

    return WebhookResponse(
        status="processing",
        message=f"Review started for PR #{pr_number}",
        pr_number=pr_number,
    )


async def _get_or_create_repo(
    db: AsyncSession,
    repo_data: dict,
    installation_id: int | None,
) -> Repository:
    """Get existing or create new repository record."""
    github_id = repo_data.get("id")
    result = await db.execute(
        select(Repository).where(Repository.github_id == github_id)
    )
    repo = result.scalar_one_or_none()

    if repo is None:
        repo = Repository(
            github_id=github_id,
            full_name=repo_data.get("full_name", ""),
            owner=repo_data.get("owner", {}).get("login", ""),
            name=repo_data.get("name", ""),
            installation_id=installation_id,
        )
        db.add(repo)
        await db.flush()
        logger.info(f"Created new repository: {repo.full_name}")
    else:
        # Update installation ID if changed
        if installation_id and repo.installation_id != installation_id:
            repo.installation_id = installation_id

    return repo


async def _get_or_create_pr(
    db: AsyncSession,
    repo: Repository,
    pr_data: dict,
) -> PullRequest:
    """Get existing or create new PR record."""
    pr_number = pr_data.get("number")
    head_sha = pr_data.get("head", {}).get("sha", "")

    result = await db.execute(
        select(PullRequest).where(
            PullRequest.repo_id == repo.id,
            PullRequest.pr_number == pr_number,
            PullRequest.head_sha == head_sha,
        )
    )
    pr = result.scalar_one_or_none()

    if pr is None:
        pr = PullRequest(
            repo_id=repo.id,
            pr_number=pr_number,
            title=pr_data.get("title", ""),
            author=pr_data.get("user", {}).get("login", ""),
            head_sha=head_sha,
            base_sha=pr_data.get("base", {}).get("sha", ""),
            head_branch=pr_data.get("head", {}).get("ref", ""),
            base_branch=pr_data.get("base", {}).get("ref", ""),
            status=PRStatus.PENDING.value,
        )
        db.add(pr)
        await db.flush()
        logger.info(f"Created PR record: #{pr_number} (sha: {head_sha[:8]})")

    return pr


async def _run_review_pipeline(
    db_url: str,
    repo_full_name: str,
    pr_number: int,
    pr_record_id: int,
    repo_id: int,
    installation_id: int | None,
    pr_title: str,
    pr_author: str,
    head_sha: str,
    base_branch: str,
    ignored_paths: list[str],
):
    """Execute the full review pipeline asynchronously.

    This runs in a background task after the webhook response is sent.
    It has its own database session since the webhook handler's session
    will be closed by then.
    """
    from app.models.database import get_session_factory

    factory = get_session_factory()

    async with factory() as db:
        try:
            # Update PR status to reviewing
            result = await db.execute(
                select(PullRequest).where(PullRequest.id == pr_record_id)
            )
            pr_record = result.scalar_one()
            pr_record.status = PRStatus.REVIEWING.value
            await db.commit()

            logger.info(f"Starting review pipeline for {repo_full_name}#{pr_number}")

            # Step 1: Fetch PR files from GitHub
            github = GitHubProvider()
            pr_files = await github.get_pr_files(
                repo_full_name, pr_number, installation_id
            )
            logger.info(f"Fetched {len(pr_files)} files from PR")

            # Step 2: Run the review pipeline
            pipeline = ReviewPipeline()
            result = await pipeline.run(
                pr_files=pr_files,
                title=pr_title,
                author=pr_author,
                base_branch=base_branch,
                ignored_paths=ignored_paths,
            )

            # Store raw diff for future fine-tuning
            raw_diff = "\n".join(
                f.patch for f in pipeline.diff_parser.parse_pr_files(pr_files) if f.patch
            )
            pr_record.diff_text = raw_diff

            all_findings = result.findings
            summary_text = result.summary
            total_tokens = result.tokens_used

            if not all_findings and result.chunks_processed == 0:
                logger.info(f"No reviewable chunks for {repo_full_name}#{pr_number}")
                pr_record.status = PRStatus.COMPLETED.value
                pr_record.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return

            logger.info(f"AI analysis complete: {len(all_findings)} findings")

            # Step 5: Save findings to database
            for finding in all_findings:
                db_finding = ReviewFinding(
                    pr_id=pr_record_id,
                    file_path=finding.file_path,
                    line_start=finding.line_start,
                    line_end=finding.line_end,
                    category=finding.category,
                    severity=finding.severity,
                    title=finding.title,
                    description=finding.description,
                    suggested_fix=finding.suggested_fix,
                )
                db.add(db_finding)

            # Save review summary
            critical_count = sum(1 for f in all_findings if f.severity == "critical")
            warning_count = sum(1 for f in all_findings if f.severity == "warning")
            suggestion_count = sum(1 for f in all_findings if f.severity == "suggestion")

            assessment = "approved"
            if critical_count > 0:
                assessment = "needs_changes"
            elif warning_count > 0:
                assessment = "minor_issues"

            db_summary = ReviewSummary(
                pr_id=pr_record_id,
                total_findings=len(all_findings),
                critical_count=critical_count,
                warning_count=warning_count,
                suggestion_count=suggestion_count,
                overall_assessment=assessment,
                summary_text=summary_text,
                tokens_used=total_tokens,
                model_used=result.model_used,
                processing_time_ms=result.processing_time_ms,
                chunks_processed=result.chunks_processed,
            )
            db.add(db_summary)

            # Step 6: Publish review to GitHub
            publisher = ReviewPublisher(github)
            comment_ids, summary_id = await publisher.publish_review(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                commit_sha=head_sha,
                findings=all_findings,
                summary_text=summary_text,
                processing_time_ms=result.processing_time_ms,
                files_reviewed=result.files_reviewed,
                installation_id=installation_id,
                pr_description=result.pr_description,
            )

            # Mark PR as completed
            pr_record.status = PRStatus.COMPLETED.value
            pr_record.completed_at = datetime.now(timezone.utc)
            await db.commit()

            # Set final commit status check
            if critical_count > 0:
                status_desc = f"{critical_count} critical, {warning_count} warnings, {suggestion_count} suggestions"
                status_state = "failure"
            elif warning_count > 0:
                status_desc = f"{warning_count} warnings, {suggestion_count} suggestions"
                status_state = "success"
            else:
                status_desc = f"No issues found — {suggestion_count} suggestions" if suggestion_count else "No issues found"
                status_state = "success"

            await github.set_commit_status(
                repo_full_name=repo_full_name,
                sha=head_sha,
                state=status_state,
                description=status_desc,
                installation_id=installation_id,
            )

            logger.info(
                f"Review pipeline complete for {repo_full_name}#{pr_number}: "
                f"{len(all_findings)} findings published"
            )

        except Exception as e:
            logger.error(
                f"Review pipeline failed for {repo_full_name}#{pr_number}: {e}",
                exc_info=True,
            )
            # Set error status on GitHub
            try:
                await github.set_commit_status(
                    repo_full_name=repo_full_name,
                    sha=head_sha,
                    state="error",
                    description="Review failed — check server logs",
                    installation_id=installation_id,
                )
            except Exception:
                pass
            try:
                pr_record.status = PRStatus.FAILED.value
                await db.commit()
            except Exception:
                pass
