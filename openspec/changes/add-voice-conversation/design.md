# Design

## Context

See `proposal.md` for motivation and the spec delta for required behavior. `add-issue-triage` decides jobs, quotes, and vendor eligibility, so the agent only collects facts and explains results. This is a four-hour build against fictional mock data with no authentication.

## Goals / Non-Goals

**Goals:**

- Complete the Truck 214 scenario by voice, from request to a booking read back and shown on screen.
- Make it impossible for the model alone to invent a price or trigger a booking.
- Report a shop failure truthfully and offer what remains.

**Non-Goals:**

- Authentication, and protection against a modified browser client.
- Real geocoding. Unknown places are reported as unknown.
- Tool execution that survives a closed tab.
- Recording or storing call audio or transcripts.

## Decisions

### Voice is an adapter over the existing services

```text
Browser (mic, speaker, transcript)
  │  ▲
  │  └─ WebRTC audio and the oai-events data channel ─► OpenAI Realtime
  ├─ POST /voice/calls (SDP offer) ─► FastAPI ─► POST /v1/realtime/calls
  └─ POST /voice/calls/{issueId}/tools/{name} ─► FastAPI ─► services ─► Postgres
```

The domain layer doesn't change.

### The server forwards the SDP offer

The backend sends the offer and session configuration to `/v1/realtime/calls` with the API key. The browser never holds a key or token, and the instructions and tool schemas aren't part of its setup request. Ephemeral client secrets were rejected because they add a credential to the browser and give no benefit here.

The model and voice are configuration, defaulting to `gpt-realtime-2.1` and `marin`.

### The browser relays tool calls

The browser reads each completed `function_call` from `response.done`, posts it to the backend, and returns the result as `function_call_output`, followed by one `response.create`. This keeps tool routes stateless and testable with `curl`, with no long-lived socket in FastAPI. A sideband connection is the better design once there's authentication, and only the transport would change.

Arguments are only acted on from `response.done`, so an interrupted response can't trigger a tool. The browser always returns a result, including on a `503` or timeout, because the model otherwise never gets an answer.

### The issue ID is bound in the URL

The model never sees or repeats a UUID for the issue, so it can't act on the wrong one.

### Tools

| Tool | Purpose | Backed by |
| --- | --- | --- |
| `update_issue` | Save what the dispatcher said, and return what's missing | `PATCH` logic, with place lookup |
| `search_shops` | Return options and exclusion reasons | Triage result |
| `prepare_booking` | Check a chosen option and return its current quote to read back | Triage result |
| `book_repair` | Create the booking | `BookingService` |

Options contain only eligible vendors, so Millrace never reaches the model as an option. Booking rejections are normal tool results, so the agent can state the real reason.

### Booking needs a code-enforced confirmation

The brief says nothing is booked before a clear yes, so instructions alone aren't enough. `book_repair` is only sent when all of these hold:

1. `prepare_booking` succeeded for the same shop, estimate, and start time.
2. The dispatcher started speaking after that result was delivered, detected from `input_audio_buffer.speech_started`.
3. The model then called `book_repair`.

Otherwise the browser refuses it locally and returns `confirmation_required` to the model. The check uses a speech event rather than the transcript, because transcription can finish after the model responds. The model still judges whether the utterance meant yes, and the on-screen confirmation card lets the dispatcher see what's being agreed. The repository's `quote_changed` check remains the final guard on price and time.

### Spoken places use a small lookup

`update_issue` takes a place as text, and the server matches it against known mock places. An unmatched place returns `location_unknown`, and the agent asks again. The model never supplies coordinates.

### The screen uses tool results

Issue and booking cards come from tool results, so the screen can't show a booking that a transcript merely mentions.

## Risks / Trade-offs

- [A modified browser could skip the confirmation gate] → This is acceptable without authentication. Moving tools to a sideband connection would close it.
- [A background voice could count as the new utterance] → The model must still judge it a yes, and the card and read-back make a mistake visible. The booking is mock data.
- [Straight-line distance understates road miles] → This is inherited from `add-issue-triage`.
- [Seeded start times can be in the past during a demo] → Reseed with times relative to the current time.

## Migration Plan

1. Finish `add-issue-triage`, then run `uv run alembic upgrade head` and reseed.
2. Add `OPENAI_API_KEY` to `.env`.

To roll back, remove the `/voice` router and the voice UI. No data changes.

## Open Questions

- Should `contact` and `symptoms` stop being required? They add two questions to a call where the brief expects only what's missing. This draft recommends making `contact` optional and filling `symptoms` from the dispatcher's opening words.
