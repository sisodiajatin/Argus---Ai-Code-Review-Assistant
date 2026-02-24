"""Pydantic schemas for dashboard API responses."""

from pydantic import BaseModel


class DashboardStats(BaseModel):
    total_repos: int = 0
    total_prs_reviewed: int = 0
    total_findings: int = 0
    critical_findings: int = 0
    avg_processing_time_ms: float = 0.0
    total_tokens_used: int = 0


class RepoListItem(BaseModel):
    id: int
    full_name: str
    owner: str
    name: str
    is_active: bool = True
    pr_count: int = 0
    last_review: str | None = None


class PRReviewListItem(BaseModel):
    id: int
    pr_number: int
    title: str | None
    author: str | None
    status: str
    findings_count: int = 0
    critical_count: int = 0
    created_at: str | None = None
    completed_at: str | None = None


class FindingItem(BaseModel):
    id: int
    file_path: str
    line_start: int | None
    line_end: int | None
    category: str
    severity: str
    title: str
    description: str
    suggested_fix: str | None = None
    feedback: str | None = None
    feedback_note: str | None = None


class ReviewDetail(BaseModel):
    pr: PRReviewListItem
    findings: list[FindingItem] = []
    summary_text: str | None = None
    overall_assessment: str | None = None
    model_used: str | None = None
    tokens_used: int = 0
    processing_time_ms: float = 0.0


class TrendDataPoint(BaseModel):
    date: str
    reviews: int = 0
    findings: int = 0


class CategoryBreakdown(BaseModel):
    category: str
    count: int = 0


class SeverityBreakdown(BaseModel):
    severity: str
    count: int = 0


class SettingsResponse(BaseModel):
    ai_model: str = ""
    ai_base_url: str = ""
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    webhook_url: str = ""
    ignored_paths: list[str] = []
    max_files_per_review: int = 50
    chunk_token_limit: int = 6000


class IgnoredPathsUpdate(BaseModel):
    ignored_paths: list[str] = []


class ReReviewResponse(BaseModel):
    status: str
    message: str


class FeedbackRequest(BaseModel):
    feedback: str  # "helpful" or "not_helpful"
    note: str | None = None


class FeedbackResponse(BaseModel):
    id: int
    feedback: str
    message: str


class FeedbackStats(BaseModel):
    total_rated: int = 0
    helpful_count: int = 0
    not_helpful_count: int = 0
    helpful_rate: float = 0.0
    by_category: list["FeedbackCategoryRate"] = []


class FeedbackCategoryRate(BaseModel):
    category: str
    total: int = 0
    helpful: int = 0
    rate: float = 0.0
