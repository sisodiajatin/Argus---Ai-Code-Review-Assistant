"""Repository database model."""

import json
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship

from app.models.database import Base


class Repository(Base):
    """Represents a GitHub repository connected to the review bot."""

    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    github_id = Column(Integer, unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False, index=True)  # e.g., "owner/repo"
    owner = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    installation_id = Column(Integer, nullable=True)
    is_active = Column(Integer, default=1)  # SQLite boolean

    # Configuration stored as JSON
    config_json = Column(Text, default="{}")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    pull_requests = relationship("PullRequest", back_populates="repository", cascade="all, delete-orphan")

    @property
    def config(self) -> dict:
        """Parse config JSON into a dictionary."""
        return json.loads(self.config_json) if self.config_json else {}

    @config.setter
    def config(self, value: dict):
        """Serialize config dictionary to JSON."""
        self.config_json = json.dumps(value)

    @property
    def ignored_paths(self) -> list[str]:
        """Get list of file path patterns to ignore during review."""
        return self.config.get("ignored_paths", [
            "*.lock",
            "*.min.js",
            "*.min.css",
            "package-lock.json",
            "yarn.lock",
            "poetry.lock",
            "*.generated.*",
            "*.pb.go",
        ])

    @property
    def review_categories(self) -> list[str]:
        """Get enabled review categories."""
        return self.config.get("review_categories", [
            "bug",
            "security",
            "performance",
            "style",
            "architecture",
        ])

    def __repr__(self) -> str:
        return f"<Repository {self.full_name}>"
