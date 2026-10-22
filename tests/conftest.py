"""Shared test fixtures and configuration."""

import os

import pytest

# Set before any test module imports app.main (which builds settings at import
# time), so the suite collects on a fresh clone with no .env file.
_TEST_ENV = {
    "GITHUB_APP_ID": "12345",
    "GITHUB_PRIVATE_KEY_PATH": "./test-key.pem",
    "GITHUB_WEBHOOK_SECRET": "test",
    "AI_API_KEY": "test-key",
    "AI_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
    # Existing API tests exercise the dashboard without logging in;
    # tests/test_security.py turns auth back on explicitly.
    "DASHBOARD_AUTH_REQUIRED": "false",
}
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY_PATH", "./test-key.pem")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
    monkeypatch.setenv("DASHBOARD_AUTH_REQUIRED", "false")


@pytest.fixture(autouse=True)
def reset_db_globals():
    """Reset the database module globals between tests to avoid stale state."""
    from app.models import database
    database._engine = None
    database._session_factory = None
    yield
    database._engine = None
    database._session_factory = None
