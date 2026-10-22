"""GitHub OAuth authentication for the dashboard."""

import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


def _oauth_configured(settings) -> bool:
    return bool(settings.github_oauth_client_id and settings.github_oauth_client_secret)


def is_user_allowed(username: str, settings=None) -> bool:
    """Whether a GitHub user may use the dashboard.

    GitHub login proves who someone is, not that they should see this
    server's reviews (which quote code from private repos). An empty
    allowlist denies everyone.
    """
    settings = settings or get_settings()
    return username.lower() in settings.dashboard_allowed_user_set


@router.get("/auth/github/login")
async def github_login(request: Request):
    """Redirect user to GitHub OAuth authorization page."""
    settings = get_settings()
    if not _oauth_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth is not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET.",
        )

    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    params = {
        "client_id": settings.github_oauth_client_id,
        "redirect_uri": str(request.url_for("github_callback")),
        "scope": "read:user",
        "state": state,
        "allow_signup": "false",
    }
    return RedirectResponse(url=f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}")


@router.get("/auth/github/callback")
async def github_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Handle GitHub OAuth callback."""
    settings = get_settings()
    if not _oauth_configured(settings):
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured")

    # Verify and consume the state (single use)
    stored_state = request.session.pop("oauth_state", "")
    if not state or not stored_state or not secrets.compare_digest(state, stored_state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    async with httpx.AsyncClient(timeout=10.0) as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        access_token = token_response.json().get("access_token") if token_response.is_success else None
        if not access_token:
            raise HTTPException(status_code=400, detail="Failed to get access token")

        user_response = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        if not user_response.is_success:
            raise HTTPException(status_code=502, detail="Failed to fetch GitHub user")
        user_data = user_response.json()

    github_id = user_data.get("id")
    username = user_data.get("login", "")
    if not github_id or not username:
        raise HTTPException(status_code=502, detail="Unexpected GitHub user response")

    if not is_user_allowed(username, settings):
        logger.warning(f"Dashboard login denied for GitHub user {username!r} (not in allowlist)")
        raise HTTPException(
            status_code=403,
            detail=f"GitHub user '{username}' is not allowed. "
            "Add it to DASHBOARD_ALLOWED_USERS on the server.",
        )

    # The OAuth token was only needed to identify the user; it is not stored.
    result = await db.execute(select(User).where(User.github_id == github_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            github_id=github_id,
            username=username,
            display_name=user_data.get("name") or username,
            avatar_url=user_data.get("avatar_url", ""),
            access_token=None,
        )
        db.add(user)
    else:
        user.username = username
        user.access_token = None
        user.avatar_url = user_data.get("avatar_url", "")
        user.last_login = datetime.now(timezone.utc)

    await db.flush()

    # Start a fresh session so nothing from before login carries over.
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["avatar_url"] = user.avatar_url or ""

    logger.info(f"User {username} logged in via GitHub OAuth")
    return RedirectResponse(url=f"{settings.frontend_url}/dashboard", status_code=302)


@router.get("/auth/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    return RedirectResponse(url=f"{get_settings().frontend_url}/login", status_code=302)


def get_current_user(request: Request) -> dict | None:
    """Get current user from session. Returns None if not logged in."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return {
        "id": user_id,
        "username": request.session.get("username", ""),
        "avatar_url": request.session.get("avatar_url", ""),
    }


def require_user(request: Request) -> dict | None:
    """Dependency guarding the dashboard API.

    Returns the logged-in user, or raises 401. When DASHBOARD_AUTH_REQUIRED is
    false (local single-user setups) everyone is let through.
    """
    settings = get_settings()
    if not settings.dashboard_auth_required:
        return get_current_user(request)
    user = get_current_user(request)
    # Re-check the allowlist so removing a user takes effect without waiting
    # for their session cookie to expire.
    if not user or not is_user_allowed(user["username"], settings):
        raise HTTPException(status_code=401, detail="Login required")
    return user


@router.get("/auth/me")
async def get_me(request: Request):
    """Return current user info for the React SPA."""
    settings = get_settings()
    user = get_current_user(request)
    return {
        "authenticated": bool(user),
        "user": user,
        "auth_required": settings.dashboard_auth_required,
        "oauth_configured": _oauth_configured(settings),
    }
