"""Health check endpoint."""

from fastapi import APIRouter

from app import __version__
from app.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint to verify the service is running."""
    return HealthResponse(status="ok", version=__version__)
