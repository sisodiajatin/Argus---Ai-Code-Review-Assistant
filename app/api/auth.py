"""GitHub OAuth authentication for the dashboard."""

import logging
import secrets

import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


@router.get("/auth/github/login")
async def github_login(request: Request):
    """Redirect user to GitHub OAuth authorization page."""
    settings = get_settings()
    client_id = getattr(settings, "github_oauth_client_id", "")
    if not client_id:
        raise HTTPException(status_code=500, detail="GitHub OAuth not configured")

    state = secrets.token_urlsafe(32)
    request.session["oauth_state"] = state

    params = {
        "client_id": client_id,
        "redirect_uri": str(request.url_for("github_callback")),
        "scope": "read:user",
        "state": state,
    }
    url = f"{GITHUB_AUTHORIZE_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
    return RedirectResponse(url=url)


@router.get("/auth/github/callback")
async def github_callback(
    request: Request,
    code: str = "",
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Handle GitHub OAuth callback."""
    settings = get_settings()

    # Verify state
    stored_state = request.session.get("oauth_state", "")
    if not state or state != stored_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    client_id = getattr(settings, "github_oauth_client_id", "")
    client_secret = getattr(settings, "github_oauth_client_secret", "")

    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        token_data = token_response.json()

    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to get access token")

    # Fetch user info from GitHub
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        user_data = user_response.json()

    github_id = user_data.get("id")
    username = user_data.get("login", "")

    # Create or update user
    result = await db.execute(select(User).where(User.github_id == github_id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            github_id=github_id,
            username=username,
            display_name=user_data.get("name", username),
            avatar_url=user_data.get("avatar_url", ""),
            access_token=access_token,
        )
        db.add(user)
    else:
        user.access_token = access_token
        user.avatar_url = user_data.get("avatar_url", "")
        from datetime import datetime, timezone
        user.last_login = datetime.now(timezone.utc)

    await db.flush()

    # Store user in session
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["avatar_url"] = user.avatar_url or ""

    logger.info(f"User {username} logged in via GitHub OAuth")
    return RedirectResponse(url="/dashboard", status_code=302)


@router.get("/auth/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


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


@router.get("/auth/me")
async def get_me(request: Request):
    """Return current user info for the React SPA."""
    user = get_current_user(request)
    if not user:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": user}
