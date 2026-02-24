"""Shared test fixtures and configuration."""

import os

import pytest


@pytest.fixture(autouse=True)
def set_test_env(monkeypatch):
    """Set required environment variables for all tests."""
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY_PATH", "./test-key.pem")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")


@pytest.fixture(autouse=True)
def reset_db_globals():
    """Reset the database module globals between tests to avoid stale state."""
    from app.models import database
    database._engine = None
    database._session_factory = None
    yield
    database._engine = None
    database._session_factory = None
