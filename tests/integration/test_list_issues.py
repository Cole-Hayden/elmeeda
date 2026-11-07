from httpx import ASGITransport, AsyncClient

from issue_tracker.application.issue_service import ISSUE_LIST_LIMIT
from issue_tracker.config import Settings
from issue_tracker.main import create_app


async def test_get_issues_lists_the_newest_first(client: AsyncClient) -> None:
    first = await client.post("/issues")
    second = await client.post("/issues")

    response = await client.get("/issues")

    assert response.status_code == 200
    listed_ids = [issue["issueId"] for issue in response.json()]
    assert listed_ids[:2] == [second.json()["issueId"], first.json()["issueId"]]


async def test_listed_issue_matches_reading_that_issue(client: AsyncClient) -> None:
    created = await client.post("/issues", json={"symptoms": "Steam from the hood."})
    issue_id = created.json()["issueId"]

    listed = (await client.get("/issues")).json()[0]

    assert listed == (await client.get(f"/issues/{issue_id}")).json()
    assert listed["details"]["symptoms"] == "Steam from the hood."


async def test_get_issues_returns_at_most_the_limit(client: AsyncClient) -> None:
    created = [await client.post("/issues") for _ in range(ISSUE_LIST_LIMIT + 1)]

    listed = (await client.get("/issues")).json()

    assert len(listed) == ISSUE_LIST_LIMIT
    assert listed[0]["issueId"] == created[-1].json()["issueId"]


async def test_issue_created_with_a_key_is_listed_once_after_a_retry(client: AsyncClient) -> None:
    headers = {"Idempotency-Key": "list-retry"}
    created = await client.post("/issues", headers=headers)
    await client.post("/issues", headers=headers)

    listed_ids = [issue["issueId"] for issue in (await client.get("/issues")).json()]

    assert listed_ids.count(created.json()["issueId"]) == 1


async def test_unreachable_database_returns_generic_503() -> None:
    unreachable_url = "postgresql+asyncpg://secret-user:secret-pass@127.0.0.1:1/secret-db"
    app = create_app(Settings(database_url=unreachable_url))

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/issues")

    assert response.status_code == 503
    assert response.json() == {"detail": "The service is temporarily unavailable."}
