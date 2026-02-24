"""FastAPI application entry point.

This is the main module that creates and configures the FastAPI application,
sets up routes, and handles startup/shutdown events.

The React dashboard (dashboard/dist/) is served as a static SPA.
All non-API routes fall through to index.html for client-side routing.
"""

import logging
import os
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
from app.config import get_settings
from app.models.database import init_db, close_db

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

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    logger.info("Argus is ready!")
    yield

    # Shutdown
    logger.info("Shutting down Argus...")
    await close_db()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

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
            "http://localhost:5173",
            "http://localhost:4173",
            "http://localhost:3000",
            os.getenv("FRONTEND_URL", ""),
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Session middleware for OAuth (uses webhook secret as signing key)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.github_webhook_secret,
    )

    # API routers
    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(webhooks_router, prefix="/api", tags=["webhooks"])
    app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])

    # Auth router (no /api prefix — used by OAuth redirects)
    app.include_router(auth_router, tags=["auth"])

    # Serve React SPA from dashboard/dist/ if the build exists
    if REACT_BUILD_DIR.is_dir():
        # Mount static assets (JS, CSS, images) under /assets
        assets_dir = REACT_BUILD_DIR / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        # Catch-all: serve index.html for any non-API route (SPA client-side routing)
        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            # Serve actual files from dist/ if they exist (favicon, etc.)
            file_path = REACT_BUILD_DIR / full_path
            if full_path and file_path.is_file():
                return FileResponse(str(file_path))
            # Otherwise serve index.html for client-side routing
            return FileResponse(str(REACT_BUILD_DIR / "index.html"))

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
