from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from issue_tracker.config import Settings
from issue_tracker.main import create_app


async def count_issues(database_url: str, issue_id: UUID) -> int:
    """Count through a separate connection, which only sees committed rows."""
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT count(*) FROM issues WHERE issue_id = :issue_id"),
            {"issue_id": issue_id},
        )
        count: int = result.scalar_one()
    await engine.dispose()
    return count


async def test_post_issue_returns_201_with_only_an_issue_id(client: AsyncClient) -> None:
    response = await client.post("/issues")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"issueId"}
    UUID(body["issueId"])


async def test_post_issue_saves_the_issue_to_the_database(
    client: AsyncClient, test_database_url: str
) -> None:
    response = await client.post("/issues")

    issue_id = UUID(response.json()["issueId"])
    assert await count_issues(test_database_url, issue_id) == 1


async def test_each_post_creates_a_distinct_issue(client: AsyncClient) -> None:
    first = await client.post("/issues")
    second = await client.post("/issues")

    assert first.json()["issueId"] != second.json()["issueId"]


async def test_client_supplied_issue_id_is_ignored(
    client: AsyncClient, test_database_url: str
) -> None:
    supplied_id = uuid4()

    response = await client.post("/issues", json={"issueId": str(supplied_id)})

    assert response.status_code == 201
    assert response.json()["issueId"] != str(supplied_id)
    assert await count_issues(test_database_url, supplied_id) == 0


async def test_unreachable_database_returns_generic_503() -> None:
    unreachable_url = "postgresql+asyncpg://secret-user:secret-pass@127.0.0.1:1/secret-db"
    app = create_app(Settings(database_url=unreachable_url))

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/issues")

    assert response.status_code == 503
    assert response.json() == {"detail": "The service is temporarily unavailable."}
