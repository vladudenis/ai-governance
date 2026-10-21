"""FastAPI application factory."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from ai_governance import __version__
from ai_governance.api.errors import install_error_handlers
from ai_governance.api.routes import router
from ai_governance.api.workflow_routes import router as workflow_router
from ai_governance.config import get_settings
from ai_governance.db.session import make_engine, make_session_factory


def create_app(database_url: str | None = None) -> FastAPI:
    """Build the API. Tests pass a database URL; the process default comes from settings."""
    url = database_url or get_settings().database_url
    engine = make_engine(url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title="AI Governance & Risk Assessment Platform",
        version=__version__,
        summary="Decision-support API for AI use cases and the EU AI Act.",
        description=(
            "Register a use case, screen the validated facts with the versioned rules engine, "
            "and read provisions from the imported act. Results are decision support. "
            "They are not a legal determination or a compliance certificate."
        ),
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.session_factory = session_factory
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(workflow_router)
    return app
