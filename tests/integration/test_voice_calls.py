from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from issue_tracker.application.voice_agent import AgentConfig, RealtimeCallError
from issue_tracker.config import Settings
from issue_tracker.infrastructure.models import IssueModel
from issue_tracker.main import create_app

TODAY = date(2026, 11, 7)


@dataclass
class FakeGateway:
    error: RealtimeCallError | None = None
    offers: list[str] = field(default_factory=list)
    agents: list[AgentConfig] = field(default_factory=list)

    async def create_call(self, sdp_offer: str, agent: AgentConfig) -> str:
        if self.error:
            raise self.error
        self.offers.append(sdp_offer)
        self.agents.append(agent)
        return "sdp-answer"


@pytest.fixture
async def app(test_database_url: str) -> AsyncIterator[FastAPI]:
    application = create_app(Settings(database_url=test_database_url), today=lambda: TODAY)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def voice_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def count_issues(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return (await session.execute(select(func.count()).select_from(IssueModel))).scalar_one()


async def post_offer(client: AsyncClient, offer: str = "sdp-offer") -> tuple[int, dict[str, str]]:
    response = await client.post(
        "/voice/calls", content=offer, headers={"Content-Type": "application/sdp"}
    )
    return response.status_code, response.json()


async def test_call_creates_an_issue_and_returns_the_answer(
    app: FastAPI,
    voice_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    gateway = FakeGateway()
    app.state.realtime_gateway = gateway
    before = await count_issues(session_factory)

    status, body = await post_offer(voice_client)

    assert status == 201
    assert body["sdp"] == "sdp-answer"
    assert UUID(body["issueId"])
    assert await count_issues(session_factory) == before + 1
    assert gateway.offers == ["sdp-offer"]
    assert "2026-11-07" in gateway.agents[0].instructions


async def test_unconfigured_voice_returns_503_and_creates_nothing(
    app: FastAPI,
    voice_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app.state.realtime_gateway = None
    before = await count_issues(session_factory)

    status, _ = await post_offer(voice_client)

    assert status == 503
    assert await count_issues(session_factory) == before


async def test_rejected_call_returns_502_and_creates_nothing(
    app: FastAPI,
    voice_client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app.state.realtime_gateway = FakeGateway(error=RealtimeCallError("Rejected."))
    before = await count_issues(session_factory)

    status, body = await post_offer(voice_client)

    assert status == 502
    assert body["detail"] == "Rejected."
    assert await count_issues(session_factory) == before


async def test_empty_offer_returns_422(app: FastAPI, voice_client: AsyncClient) -> None:
    gateway = FakeGateway()
    app.state.realtime_gateway = gateway

    status, _ = await post_offer(voice_client, offer="  ")

    assert status == 422
    assert gateway.offers == []
