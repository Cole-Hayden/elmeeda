# Proposal

## Why

The backend can triage an issue and quote vendors, but nobody can talk to it. The brief requires a browser voice agent that takes a dispatcher from request to confirmation, books nothing before a clear yes, and stays truthful when a shop fails.

## What Changes

- Add a browser voice call using OpenAI's Realtime API over WebRTC, with speech in and speech out.
- Add `POST /voice/calls`, which creates an issue and connects the call while keeping the API key on the server.
- Add `POST /voice/calls/{issueId}/tools/{name}`, which runs the agent's tools against the application services.
- Add a server-side lookup that turns a known spoken place into coordinates.
- Require a prepared booking and a new dispatcher utterance before any booking is sent.
- Show the live transcript, the issue's state, and the booking on screen, using tool results rather than the transcript.

## Capabilities

### New Capabilities

- `voice-conversation`: Call setup, agent tools, the confirmation gate, and truthful failure handling.

### Modified Capabilities

None.

## Impact

- **Code**: API, application, and infrastructure layers; the React UI; agent instructions and tool schemas.
- **APIs**: New `/voice` routes. Existing routes are unchanged.
- **Database**: None.
- **Dependencies**: `httpx` moves from development to runtime. No new frontend packages.
- **Configuration**: `OPENAI_API_KEY`, which is optional so that tests and non-voice routes run without it.
- **Ordering**: `add-issue-triage` must be finished first, because the tools use its triage result.
