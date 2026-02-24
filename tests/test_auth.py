"""Tests for the authentication module."""

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.api.auth import get_current_user


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestGetCurrentUser:
    def test_no_session_returns_none(self):
        request = MagicMock()
        request.session = {}
        result = get_current_user(request)
        assert result is None

    def test_with_session_returns_user(self):
        request = MagicMock()
        request.session = {
            "user_id": 42,
            "username": "testuser",
            "avatar_url": "https://avatars.example.com/42",
        }
        result = get_current_user(request)
        assert result["id"] == 42
        assert result["username"] == "testuser"
        assert result["avatar_url"] == "https://avatars.example.com/42"

    def test_partial_session_returns_defaults(self):
        request = MagicMock()
        request.session = {"user_id": 1}
        result = get_current_user(request)
        assert result["id"] == 1
        assert result["username"] == ""
        assert result["avatar_url"] == ""


class TestOAuthEndpoints:
    def test_github_login_no_client_id(self, client):
        """OAuth login should fail when client ID is not configured."""
        response = client.get("/auth/github/login", follow_redirects=False)
        # Should return 500 since OAuth is not configured
        assert response.status_code == 500

    def test_github_callback_invalid_state(self, client):
        """OAuth callback should reject invalid state."""
        response = client.get(
            "/auth/github/callback?code=test&state=invalid",
            follow_redirects=False,
        )
        assert response.status_code == 400

    def test_logout_redirects(self, client):
        """Logout should redirect to login page."""
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code == 302
        assert "/login" in response.headers["location"]

    def test_me_unauthenticated(self, client):
        """GET /auth/me should return unauthenticated when no session."""
        response = client.get("/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["user"] is None
