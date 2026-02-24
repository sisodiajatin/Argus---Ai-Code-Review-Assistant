"""User database model for GitHub OAuth."""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime

from app.models.database import Base


class User(Base):
    """A user authenticated via GitHub OAuth."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    github_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    access_token = Column(String(255), nullable=True)  # GitHub OAuth token

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<User {self.username}>"
