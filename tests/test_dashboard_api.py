"""Tests for the dashboard API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.database import init_db, close_db, get_engine


@pytest.fixture
def client():
    """Create a test client with database tables initialized."""
    # Use the app's lifespan by entering the TestClient context manager
    with TestClient(app) as c:
        yield c


class TestDashboardStats:
    def test_get_stats(self, client):
        response = client.get("/api/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_repos" in data
        assert "total_prs_reviewed" in data
        assert "total_findings" in data
        assert "critical_findings" in data
        assert "avg_processing_time_ms" in data
        assert "total_tokens_used" in data
        # Values should be non-negative integers/floats
        assert data["total_repos"] >= 0
        assert data["total_prs_reviewed"] >= 0


class TestDashboardRepos:
    def test_list_repos(self, client):
        response = client.get("/api/dashboard/repos")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestDashboardReviews:
    def test_list_reviews_for_nonexistent_repo(self, client):
        response = client.get("/api/dashboard/repos/99999/reviews")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_get_review_detail_not_found(self, client):
        response = client.get("/api/dashboard/reviews/99999")
        assert response.status_code == 404


class TestDashboardAnalytics:
    def test_get_trends(self, client):
        response = client.get("/api/dashboard/analytics/trends")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_trends_custom_days(self, client):
        response = client.get("/api/dashboard/analytics/trends?days=7")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_category_breakdown(self, client):
        response = client.get("/api/dashboard/analytics/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_severity_breakdown(self, client):
        response = client.get("/api/dashboard/analytics/severity")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestDashboardSettings:
    def test_get_settings(self, client):
        response = client.get("/api/dashboard/settings")
        assert response.status_code == 200
        data = response.json()
        assert "ai_model" in data
        assert "ai_base_url" in data
        assert "webhook_url" in data
        assert "max_files_per_review" in data
        assert "chunk_token_limit" in data
        assert data["max_files_per_review"] > 0

    def test_settings_no_secrets_exposed(self, client):
        response = client.get("/api/dashboard/settings")
        data = response.json()
        # Ensure no API keys or secrets are in the response
        response_str = str(data)
        assert "api_key" not in response_str.lower()
        assert "secret" not in response_str.lower()
        assert "private_key" not in response_str.lower()


class TestReReview:
    def test_re_review_not_found(self, client):
        response = client.post("/api/dashboard/reviews/99999/re-review")
        assert response.status_code == 404

    def test_settings_serves_spa(self, client):
        response = client.get("/settings")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestSPARouting:
    """Test that non-API routes serve the React SPA index.html."""

    def test_root_serves_spa(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_dashboard_serves_spa(self, client):
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_login_serves_spa(self, client):
        response = client.get("/login")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_repos_serves_spa(self, client):
        response = client.get("/repos")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_analytics_serves_spa(self, client):
        response = client.get("/analytics")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
