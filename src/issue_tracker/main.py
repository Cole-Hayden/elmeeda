import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issue_tracker.api.issues import router as issues_router
from issue_tracker.application.ports import StorageUnavailableError
from issue_tracker.config import Settings

logger = logging.getLogger(__name__)


async def handle_storage_unavailable(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Storage unavailable during %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "The service is temporarily unavailable."},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(resolved_settings.database_url, pool_pre_ping=True)
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        yield
        await engine.dispose()

    app = FastAPI(title="Issue Tracker", lifespan=lifespan)
    app.add_exception_handler(StorageUnavailableError, handle_storage_unavailable)
    app.include_router(issues_router)
    return app
