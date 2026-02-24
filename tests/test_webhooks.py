"""Tests for the webhook handler."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _post_with_signature(client, payload: dict, event: str = "pull_request", secret: str = "test"):
    """Post a webhook payload with a valid signature.

    Uses the exact same bytes the TestClient will send, ensuring
    the HMAC signature matches.
    """
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    return client.post(
        "/api/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": event,
            "X-Hub-Signature-256": f"sha256={sig}",
        },
    )


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"


class TestWebhookSignature:
    def test_missing_signature_rejected(self, client):
        response = client.post(
            "/api/webhooks/github",
            json={"action": "opened"},
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert response.status_code == 401

    def test_invalid_signature_rejected(self, client):
        response = client.post(
            "/api/webhooks/github",
            json={"action": "opened"},
            headers={
                "X-GitHub-Event": "pull_request",
                "X-Hub-Signature-256": "sha256=invalid",
            },
        )
        assert response.status_code == 401


class TestWebhookEventFiltering:
    def test_non_pr_event_ignored(self, client):
        payload = {"action": "created"}
        response = _post_with_signature(client, payload, event="issues")

        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    def test_non_reviewable_action_ignored(self, client):
        payload = {"action": "closed"}
        response = _post_with_signature(client, payload, event="pull_request")

        assert response.status_code == 200
        assert response.json()["status"] == "ignored"
