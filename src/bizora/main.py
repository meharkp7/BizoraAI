
"""Bizora FastAPI application entry point."""

import sys

from dotenv import load_dotenv
from fastapi import FastAPI

from bizora.api import register_error_handlers, router

if "pytest" not in sys.modules:
    load_dotenv()

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
