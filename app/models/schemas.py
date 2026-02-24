"""Pydantic schemas for API request/response validation."""

from datetime import datetime, timezone
from pydantic import BaseModel, Field


# --- Webhook Schemas ---

class WebhookPayload(BaseModel):
    """Raw GitHub webhook payload (partial, relevant fields only)."""
    action: str
    number: int | None = None
    pull_request: dict | None = None
    repository: dict | None = None
    installation: dict | None = None
    sender: dict | None = None


# --- Internal Data Schemas ---

class FileChange(BaseModel):
    """Represents a single file change in a diff."""
    file_path: str
    status: str  # added, modified, deleted, renamed
    old_path: str | None = None  # for renames
    additions: int = 0
    deletions: int = 0
    patch: str = ""  # raw patch/diff text
    hunks: list["DiffHunk"] = []


class DiffHunk(BaseModel):
    """A single hunk within a file diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str = ""
    lines: list["DiffLine"] = []


class DiffLine(BaseModel):
    """A single line within a diff hunk."""
    content: str
    line_type: str  # "add", "delete", "context"
    old_line_number: int | None = None
    new_line_number: int | None = None


class ReviewChunk(BaseModel):
    """A chunk of code prepared for LLM analysis."""
    chunk_id: str
    files: list[FileChange]
    context_summary: str = ""
    total_tokens_estimate: int = 0
    priority_score: float = 0.0


class AIFinding(BaseModel):
    """A finding returned by the AI analyzer."""
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    category: str
    severity: str
    title: str
    description: str
    suggested_fix: str | None = None


class AIReviewResult(BaseModel):
    """Complete result from AI analysis of a chunk."""
    findings: list[AIFinding] = []
    summary: str = ""
    tokens_used: int = 0


# --- API Response Schemas ---

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: str = "0.1.0"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WebhookResponse(BaseModel):
    """Webhook processing response."""
    status: str
    message: str
    pr_number: int | None = None
