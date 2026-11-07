import json
import logging

import httpx

from issue_tracker.application.voice_agent import AgentConfig, RealtimeCallError

logger = logging.getLogger(__name__)

CALLS_URL = "https://api.openai.com/v1/realtime/calls"
TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
TIMEOUT_SECONDS = 15.0


class OpenAIRealtimeGateway:
    def __init__(
        self,
        api_key: str,
        model: str,
        voice: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self._transport = transport

    async def create_call(self, sdp_offer: str, agent: AgentConfig) -> str:
        session = {
            "type": "realtime",
            "model": self._model,
            "instructions": agent.instructions,
            "tools": list(agent.tools),
            "tool_choice": "auto",
            "audio": {
                "input": {"transcription": {"model": TRANSCRIPTION_MODEL}},
                "output": {"voice": self._voice},
            },
        }
        # Sending both as files makes httpx use multipart, which this endpoint requires.
        form = {"sdp": (None, sdp_offer), "session": (None, json.dumps(session))}
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=TIMEOUT_SECONDS
            ) as client:
                response = await client.post(
                    CALLS_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files=form,
                )
        except httpx.HTTPError as exc:
            logger.error("Couldn't reach OpenAI Realtime: %s", type(exc).__name__)
            raise RealtimeCallError("Couldn't reach the voice service.") from None
        if response.is_error:
            logger.error(
                "OpenAI Realtime rejected the call: %s %s", response.status_code, response.text
            )
            raise RealtimeCallError("The voice service rejected the call.")
        return response.text
