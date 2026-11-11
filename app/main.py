"""FastAPI application for Payment Cascading System Demo."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.payments import router as payments_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init and cleanup."""
    logger.info("Payment Cascading System Demo starting")
    # TODO: Initialize database connection, Redis broker, etc.
    yield
    logger.info("Payment Cascading System Demo shutting down")
    # TODO: Cleanup resources


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Payment Cascading System Demo",
        version="0.1.0",
        description="Demo service for cascading payments with Stripe Sandbox",
        lifespan=lifespan,
    )

    # Include routers
    app.include_router(payments_router)

    return app


# Module-level app instance for gunicorn/uvicorn
app = create_app()


def main() -> None:
    """Entry point for running the demo."""
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
