"""Security regression tests for the server.

Each test here pins down a vulnerability that existed in an earlier version.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import _resolve_spa_file, create_app

TRAVERSAL_PATHS = [
    "/..%2F..%2Fapp%2Fconfig.py",
    "/%2e%2e/%2e%2e/app/config.py",
    "/..%2f..%2f.env",
    "/..%2F..%2F..%2F..%2F..%2F..%2Fetc%2Fpasswd",
    "/assets/..%2F..%2Fsecret.txt",
    "/%2e%2e%2fsecret.txt",
]


@pytest.fixture
def dist(tmp_path):
    """A fake React build with a secret file sitting next to it."""
    build = tmp_path / "project" / "dashboard" / "dist"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text("<!doctype html><title>Argus SPA</title>")
    (build / "favicon.svg").write_text("<svg/>")
    (build / "assets" / "app.js").write_text("console.log('app')")
    (tmp_path / "project" / "secret.txt").write_text("TOP-SECRET")
    (tmp_path / "project" / "dashboard" / "secret.txt").write_text("TOP-SECRET")
    return build


@pytest.fixture
def spa_client(dist):
    with TestClient(create_app(build_dir=dist)) as c:
        yield c


class TestSPAPathTraversal:
    @pytest.mark.parametrize("path", TRAVERSAL_PATHS)
    def test_traversal_never_leaks_files(self, spa_client, path):
        response = spa_client.get(path)
        assert "TOP-SECRET" not in response.text
        assert "root:x:0:0" not in response.text
        assert "Application configuration" not in response.text

    def test_real_files_inside_dist_still_served(self, spa_client):
        response = spa_client.get("/favicon.svg")
        assert response.status_code == 200
        assert response.text == "<svg/>"

    def test_unknown_routes_get_index(self, spa_client):
        response = spa_client.get("/repos/42")
        assert response.status_code == 200
        assert "Argus SPA" in response.text

    def test_resolver_rejects_parent_paths(self, dist):
        assert _resolve_spa_file(dist, "../secret.txt") == dist.resolve() / "index.html"
        assert _resolve_spa_file(dist, "../../secret.txt") == dist.resolve() / "index.html"

    def test_resolver_rejects_symlink_escape(self, dist, tmp_path):
        outside = tmp_path / "outside.txt"
        outside.write_text("TOP-SECRET")
        (dist / "link.txt").symlink_to(outside)
        assert _resolve_spa_file(dist, "link.txt") == dist.resolve() / "index.html"


# ─── Dashboard authentication ───

from unittest.mock import MagicMock, patch  # noqa: E402

from app.main import app  # noqa: E402

DASHBOARD_ENDPOINTS = [
    ("GET", "/api/dashboard/stats"),
    ("GET", "/api/dashboard/repos"),
    ("GET", "/api/dashboard/repos/1/reviews"),
    ("GET", "/api/dashboard/reviews/1"),
    ("POST", "/api/dashboard/reviews/1/re-review"),
    ("GET", "/api/dashboard/settings"),
    ("GET", "/api/dashboard/analytics/trends"),
    ("GET", "/api/dashboard/analytics/categories"),
    ("GET", "/api/dashboard/analytics/severity"),
    ("GET", "/api/dashboard/analytics/feedback"),
    ("POST", "/api/dashboard/findings/1/feedback"),
]


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("DASHBOARD_AUTH_REQUIRED", "true")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "cid")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("DASHBOARD_ALLOWED_USERS", "Alice, bob")


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class _FakeResponse:
    def __init__(self, data, ok=True):
        self._data = data
        self.is_success = ok

    def json(self):
        return self._data


class _FakeHTTPX:
    """Stands in for httpx.AsyncClient during the OAuth callback."""

    def __init__(self, login):
        self.login = login

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        return _FakeResponse({"access_token": "gho_test"})

    async def get(self, url, **kwargs):
        return _FakeResponse({"id": 1000 + len(self.login), "login": self.login,
                              "name": self.login, "avatar_url": ""})


def _login(client, username):
    """Run the real OAuth flow against a faked GitHub."""
    login = client.get("/auth/github/login", follow_redirects=False)
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    with patch("app.api.auth.httpx.AsyncClient", _FakeHTTPX(username)):
        return client.get(f"/auth/github/callback?code=c&state={state}", follow_redirects=False)


class TestDashboardAuth:
    @pytest.mark.parametrize("method,path", DASHBOARD_ENDPOINTS)
    def test_unauthenticated_requests_rejected(self, auth_env, client, method, path):
        response = client.request(method, path, json={"feedback": "helpful"})
        assert response.status_code == 401

    def test_health_and_webhook_stay_public(self, auth_env, client):
        assert client.get("/api/health").status_code == 200
        # Webhook is protected by its HMAC signature, not by login
        assert client.post("/api/webhooks/github", content=b"{}").status_code == 401  # bad signature

    def test_allowed_user_can_log_in_and_use_api(self, auth_env, client):
        response = _login(client, "alice")  # allowlist is case-insensitive
        assert response.status_code == 302
        assert client.get("/api/dashboard/stats").status_code == 200
        me = client.get("/auth/me").json()
        assert me["authenticated"] is True
        assert me["user"]["username"] == "alice"

    def test_user_not_in_allowlist_is_refused(self, auth_env, client):
        response = _login(client, "mallory")
        assert response.status_code == 403
        assert client.get("/api/dashboard/stats").status_code == 401

    def test_empty_allowlist_denies_everyone(self, auth_env, client, monkeypatch):
        monkeypatch.setenv("DASHBOARD_ALLOWED_USERS", "")
        assert _login(client, "alice").status_code == 403

    def test_removed_user_loses_access_without_new_login(self, auth_env, client, monkeypatch):
        _login(client, "bob")
        assert client.get("/api/dashboard/stats").status_code == 200
        monkeypatch.setenv("DASHBOARD_ALLOWED_USERS", "alice")
        assert client.get("/api/dashboard/stats").status_code == 401

    def test_oauth_state_is_single_use(self, auth_env, client):
        login = client.get("/auth/github/login", follow_redirects=False)
        from urllib.parse import parse_qs, urlparse
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
        with patch("app.api.auth.httpx.AsyncClient", _FakeHTTPX("alice")):
            first = client.get(f"/auth/github/callback?code=c&state={state}", follow_redirects=False)
            client.get("/auth/logout")
            replay = client.get(f"/auth/github/callback?code=c&state={state}", follow_redirects=False)
        assert first.status_code == 302
        assert replay.status_code == 400

    def test_oauth_token_not_persisted(self, auth_env, client):
        import asyncio
        from sqlalchemy import select
        from app.models.database import get_session_factory
        from app.models.user import User

        _login(client, "alice")

        async def tokens():
            async with get_session_factory()() as db:
                return (await db.execute(select(User.access_token))).scalars().all()

        assert all(t is None for t in asyncio.run(tokens()))

    def test_login_redirect_url_is_encoded(self, auth_env, client):
        location = client.get("/auth/github/login", follow_redirects=False).headers["location"]
        assert "redirect_uri=http%3A%2F%2F" in location


class TestSessionAndCORS:
    def test_session_key_is_not_the_webhook_secret(self):
        from app.config import get_settings
        settings = get_settings()
        assert settings.effective_session_secret != settings.github_webhook_secret

    def test_explicit_session_secret_wins(self, monkeypatch):
        from app.config import get_settings
        monkeypatch.setenv("SESSION_SECRET", "explicit")
        assert get_settings().effective_session_secret == "explicit"

    def test_empty_frontend_url_is_not_an_allowed_origin(self, client):
        response = client.options(
            "/api/health",
            headers={"Origin": "null", "Access-Control-Request-Method": "GET"},
        )
        assert response.headers.get("access-control-allow-origin") != "null"


class TestStartupValidation:
    def test_missing_ai_key_fails_fast(self, monkeypatch):
        monkeypatch.setenv("AI_API_KEY", "")
        with pytest.raises(RuntimeError, match="AI_API_KEY"):
            with TestClient(create_app()):
                pass

    def test_sqlite_directory_is_created(self, tmp_path):
        from app.config import ensure_sqlite_dir
        db = tmp_path / "nested" / "dir" / "argus.db"
        ensure_sqlite_dir(f"sqlite+aiosqlite:///{db}")
        assert db.parent.is_dir()
