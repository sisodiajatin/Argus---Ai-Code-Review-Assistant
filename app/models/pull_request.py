"""Pull Request database model."""

from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship

from app.models.database import Base


class PRStatus(str, PyEnum):
    """Status of a pull request review."""
    PENDING = "pending"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"


class PullRequest(Base):
    """Represents a pull request being reviewed."""

    __tablename__ = "pull_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    repo_id = Column(Integer, ForeignKey("repositories.id"), nullable=False, index=True)
    pr_number = Column(Integer, nullable=False)
    title = Column(String(500), nullable=True)
    author = Column(String(255), nullable=True)
    head_sha = Column(String(40), nullable=False)
    base_sha = Column(String(40), nullable=True)
    head_branch = Column(String(255), nullable=True)
    base_branch = Column(String(255), nullable=True)
    status = Column(String(20), default=PRStatus.PENDING.value)
    diff_text = Column(Text, nullable=True)  # Store raw diff for future fine-tuning

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    repository = relationship("Repository", back_populates="pull_requests")
    findings = relationship("ReviewFinding", back_populates="pull_request", cascade="all, delete-orphan")
    summary = relationship("ReviewSummary", back_populates="pull_request", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<PullRequest #{self.pr_number} ({self.status})>"
