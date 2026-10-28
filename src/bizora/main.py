
"""Bizora FastAPI application entry point."""

import sys

from dotenv import load_dotenv
from fastapi import FastAPI

from bizora.api import register_error_handlers, router
from bizora.contracts.run import ExperimentRun
from bizora.db.repository import experiment_run_from_record, get_experiment_run
from bizora.db.session import get_session_factory
from bizora.streaming.bus import get_shared_bus
from bizora.streaming.router import create_streaming_router

if "pytest" not in sys.modules:
    load_dotenv()


def load_experiment_run(run_id: str) -> ExperimentRun | None:
    """Load one run for the telemetry router's unknown-run guard."""
    session = get_session_factory()()
    try:
        record = get_experiment_run(session, run_id)
        if record is None:
            return None
        return experiment_run_from_record(record)
    finally:
        session.close()


app = FastAPI(
    title="Bizora API",
    version="0.1.0",
    description=(
        "Evidence-linked methodology graphs and versioned "
        "research architecture workflows."
    ),
)

app.include_router(router)
app.include_router(create_streaming_router(get_shared_bus(), get_run=load_experiment_run))
register_error_handlers(app)
