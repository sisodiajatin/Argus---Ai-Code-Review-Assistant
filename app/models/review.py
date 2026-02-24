"""Review findings and summary database models."""

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship

from app.models.database import Base


class FindingCategory(str, PyEnum):
    """Category of a review finding."""
    BUG = "bug"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    ARCHITECTURE = "architecture"


class FindingSeverity(str, PyEnum):
    """Severity level of a review finding."""
    CRITICAL = "critical"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class FindingFeedback(str, PyEnum):
    """Developer feedback on a finding's usefulness."""
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"


class ReviewFinding(Base):
    """An individual review finding/comment on a PR."""

    __tablename__ = "review_findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pr_id = Column(Integer, ForeignKey("pull_requests.id"), nullable=False, index=True)

    # Location
    file_path = Column(String(500), nullable=False)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    side = Column(String(10), default="RIGHT")

    # Finding details
    category = Column(String(20), nullable=False)
    severity = Column(String(20), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    suggested_fix = Column(Text, nullable=True)
    code_snippet = Column(Text, nullable=True)

    # GitHub tracking
    github_comment_id = Column(Integer, nullable=True)
    is_posted = Column(Integer, default=0)

    # Developer feedback
    feedback = Column(String(20), nullable=True)
    feedback_note = Column(Text, nullable=True)
    feedback_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    pull_request = relationship("PullRequest", back_populates="findings")

    def __repr__(self) -> str:
        return f"<ReviewFinding [{self.severity}] {self.category}: {self.title}>"


class ReviewSummary(Base):
    """Summary of the overall review for a PR."""

    __tablename__ = "review_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pr_id = Column(Integer, ForeignKey("pull_requests.id"), nullable=False, unique=True)

    # Counts
    total_findings = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    suggestion_count = Column(Integer, default=0)

    # Assessment
    overall_assessment = Column(String(50), nullable=True)  # e.g., "needs_changes", "approved", "minor_issues"
    summary_text = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)  # JSON array of positive observations

    # Metadata for fine-tuning tracking
    tokens_used = Column(Integer, default=0)
    model_used = Column(String(50), nullable=True)
    processing_time_ms = Column(Float, default=0)
    chunks_processed = Column(Integer, default=0)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    pull_request = relationship("PullRequest", back_populates="summary")

    def __repr__(self) -> str:
        return f"<ReviewSummary PR#{self.pr_id}: {self.overall_assessment}>"
