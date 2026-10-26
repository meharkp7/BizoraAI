
"""Bizora FastAPI application entry point."""

from fastapi import FastAPI

from bizora.api import register_error_handlers, router

app = FastAPI(
    title="Bizora API",
    version="0.1.0",
    description=(
        "Evidence-linked methodology graphs and versioned "
        "research architecture workflows."
    ),
)

app.include_router(router)
register_error_handlers(app)
