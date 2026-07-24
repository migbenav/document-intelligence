"""FastAPI application factory."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Document Intelligence API",
        version="0.1.0",
        description="Document ingestion and analysis API",
    )
    return app
