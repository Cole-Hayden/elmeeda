import json
from datetime import date
from email.parser import BytesParser
from email.policy import default

import httpx
import pytest

from issue_tracker.application.voice_agent import (
    TOOLS,
    AgentConfig,
    RealtimeCallError,
    agent_config,
)
from issue_tracker.domain.issue import ProblemType
from issue_tracker.infrastructure.openai_realtime import OpenAIRealtimeGateway

API_KEY = "test-key-not-real"
AGENT = AgentConfig(instructions="Be brief.", tools=TOOLS)


def gateway(transport: httpx.AsyncBaseTransport) -> OpenAIRealtimeGateway:
    return OpenAIRealtimeGateway(API_KEY, "test-model", "test-voice", transport=transport)


def multipart_fields(request: httpx.Request) -> dict[str, str]:
    header = f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
    message = BytesParser(policy=default).parsebytes(header + request.content)
    return {
        str(part.get_param("name", header="content-disposition")): str(part.get_content())
        for part in message.iter_parts()
    }


async def test_create_call_sends_offer_and_session_and_returns_answer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, text="sdp-answer")

    answer = await gateway(httpx.MockTransport(handler)).create_call("sdp-offer", AGENT)

    assert answer == "sdp-answer"
    request = seen[0]
    assert str(request.url) == "https://api.openai.com/v1/realtime/calls"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    fields = multipart_fields(request)
    assert fields["sdp"].strip() == "sdp-offer"
    session = json.loads(fields["session"])
    assert session["type"] == "realtime"
    assert session["model"] == "test-model"
    assert session["audio"]["output"]["voice"] == "test-voice"
    assert session["instructions"] == "Be brief."
    assert [tool["name"] for tool in session["tools"]] == [
        "update_issue",
        "search_shops",
        "prepare_booking",
        "book_repair",
    ]


async def test_rejected_call_raises_without_exposing_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad session"}})

    with pytest.raises(RealtimeCallError) as caught:
        await gateway(httpx.MockTransport(handler)).create_call("sdp-offer", AGENT)

    assert API_KEY not in str(caught.value)


async def test_unreachable_service_raises_without_exposing_the_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed with {API_KEY}", request=request)

    with pytest.raises(RealtimeCallError) as caught:
        await gateway(httpx.MockTransport(handler)).create_call("sdp-offer", AGENT)

    assert API_KEY not in str(caught.value)
    assert caught.value.__cause__ is None


def test_agent_config_states_the_date_and_every_problem() -> None:
    config = agent_config(date(2026, 11, 7))

    assert "2026-11-07" in config.instructions
    update_issue = next(tool for tool in config.tools if tool["name"] == "update_issue")
    parameters = update_issue["parameters"]
    assert isinstance(parameters, dict)
    assert parameters["properties"]["problem"]["enum"] == [p.value for p in ProblemType]
