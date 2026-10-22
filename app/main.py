"""FastAPI application entry point.

This is the main module that creates and configures the FastAPI application,
sets up routes, and handles startup/shutdown events.

The React dashboard (dashboard/dist/) is served as a static SPA.
All non-API routes fall through to index.html for client-side routing.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.webhooks import router as webhooks_router
from app.api.health import router as health_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.config import ensure_sqlite_dir, get_settings
from app.models.database import init_db, close_db
from app.services.background import shutdown_background_tasks

# Path to the React build output
REACT_BUILD_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "dist"


def setup_logging():
    """Configure application logging."""
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    # Quiet down noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown."""
    # Startup
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting Argus — The All-Seeing Code Reviewer...")

    settings = get_settings()
    # Fail fast: without an AI key every review would fail at runtime.
    if not settings.ai_api_key:
        raise RuntimeError(
            "AI_API_KEY is not set. Argus cannot review pull requests without it."
        )
    if not settings.session_secret:
        logger.warning(
            "SESSION_SECRET is not set; deriving the session key from the webhook secret. "
            "Set SESSION_SECRET explicitly in production."
        )

    # Initialize database
    ensure_sqlite_dir(settings.database_url)
    await init_db()
    logger.info("Database initialized")

    logger.info("Argus is ready!")
    yield

    # Shutdown
    logger.info("Shutting down Argus...")
    await shutdown_background_tasks()
    await close_db()
    logger.info("Shutdown complete")


def _resolve_spa_file(build_dir: Path, full_path: str) -> Path:
    """Map a request path to a file inside build_dir, falling back to index.html.

    Paths that resolve outside build_dir (e.g. encoded ``../`` sequences) never
    reach the filesystem: they get index.html like any unknown client route.
    """
    root = build_dir.resolve()
    if full_path:
        candidate = (root / full_path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return candidate
    return root / "index.html"


def create_app(build_dir: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    spa_dir = build_dir or REACT_BUILD_DIR

    app = FastAPI(
        title="Argus — The All-Seeing Code Reviewer",
        description=(
            "An AI-powered code review bot that integrates with GitHub pull requests "
            "to provide intelligent review suggestions including bug detection, "
            "security analysis, and architectural improvements."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware for React frontend (dev server + production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin
            for origin in (
                "http://localhost:5173",
                "http://localhost:4173",
                "http://localhost:3000",
                settings.frontend_url,
            )
            if origin
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Session middleware for OAuth — signed with its own key, not the webhook secret
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.effective_session_secret,
        same_site="lax",
        https_only=settings.public_url.startswith("https://"),
    )

    # API routers
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(webhooks_router, prefix="/api", tags=["webhooks"])
    app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])

    # Auth router (no /api prefix — used by OAuth redirects)
    app.include_router(auth_router, tags=["auth"])

    # Serve React SPA from dashboard/dist/ if the build exists
    if spa_dir.is_dir():
        # Mount static assets (JS, CSS, images) under /assets
        assets_dir = spa_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # Catch-all: serve index.html for any non-API route (SPA client-side routing)
        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            # Real files inside dist/ (favicon, etc.) are served directly;
            # anything else gets index.html for client-side routing.
            return FileResponse(str(_resolve_spa_file(spa_dir, full_path)))

    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
        log_level=settings.log_level,
    )
