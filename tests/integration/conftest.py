import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from issue_tracker.config import Settings
from issue_tracker.infrastructure.seed import reset_mock_data
from issue_tracker.main import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def recreate_database(admin_url: str, database: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        await connection.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        await connection.execute(text(f'CREATE DATABASE "{database}"'))
    await engine.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Create and migrate a dedicated test database, leaving development data alone."""
    admin_url = make_url(Settings().database_url)
    database = f"{admin_url.database}_test"
    asyncio.run(recreate_database(admin_url.render_as_string(hide_password=False), database))

    url = admin_url.set(database=database).render_as_string(hide_password=False)
    config = Config(PROJECT_ROOT / "alembic.ini")
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    return url


@pytest.fixture
async def session_factory(
    test_database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory for a database reset to the start of the mock scenario."""
    engine = create_async_engine(test_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await reset_mock_data(factory)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(test_database_url: str) -> AsyncIterator[AsyncClient]:
    app = create_app(Settings(database_url=test_database_url))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client
