import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from issue_tracker.api.issues import router as issues_router
from issue_tracker.api.voice import router as voice_router
from issue_tracker.application.clock import central_today
from issue_tracker.application.ports import StorageUnavailableError
from issue_tracker.application.shop_checks import ShopChecker
from issue_tracker.config import Settings
from issue_tracker.infrastructure.openai_realtime import OpenAIRealtimeGateway

logger = logging.getLogger(__name__)


async def handle_storage_unavailable(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Storage unavailable during %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "The service is temporarily unavailable."},
    )


def create_app(
    settings: Settings | None = None, today: Callable[[], date] = central_today
) -> FastAPI:
    resolved_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(resolved_settings.database_url, pool_pre_ping=True)
        app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
        yield
        await engine.dispose()

    app = FastAPI(title="Issue Tracker", lifespan=lifespan)
    app.state.today = today
    app.state.shop_checker = ShopChecker(resolved_settings.shop_timeout_seconds)
    api_key = resolved_settings.openai_api_key
    app.state.realtime_gateway = (
        OpenAIRealtimeGateway(
            api_key.get_secret_value(),
            resolved_settings.openai_realtime_model,
            resolved_settings.openai_realtime_voice,
        )
        if api_key and api_key.get_secret_value()
        else None
    )
    app.add_exception_handler(StorageUnavailableError, handle_storage_unavailable)
    if resolved_settings.enable_dev_api:
        app.include_router(issues_router)
    app.include_router(voice_router)
    return app
