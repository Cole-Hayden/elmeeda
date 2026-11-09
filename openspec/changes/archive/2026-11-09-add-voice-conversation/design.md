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
| `prepare_booking` | Check a chosen option, hold its quote for confirmation, and return it to read back | Triage result, `booking_confirmations` |
| `book_repair` | Create the confirmed booking | `BookingService` |

Options contain only eligible vendors, so Millrace never reaches the model as an option. Booking rejections and shop failures are normal tool results, so the agent can state the real reason.

### Booking needs a code-enforced confirmation

The brief says nothing is booked before a clear yes, so instructions alone aren't enough. The backend decides, using state the model can't write:

1. `prepare_booking` stores the shop, estimate, and start time in `booking_confirmations`, unconfirmed, with a new `confirmationId`. Preparing again replaces it.
2. When an agent response finishes playing (`output_audio_buffer.stopped`), the browser posts its transcript to `POST /voice/calls/{id}/read-backs`. The backend marks the booking as read back once a transcript contains the prepared shop, estimate, and start time. Later speech doesn't undo this, so "booking that now" can't cancel a booking the dispatcher agreed to.
3. The browser posts the transcript of the dispatcher's reply to `POST /voice/calls/{id}/answers`. Neither route is a tool, so the model can't call them, and the model never sees the `confirmationId`.
4. A small classifier in the domain layer reads the reply. Any negative word wins, a question is unclear, and only a clear yes confirms. A yes to a booking that hasn't been read back records as no, so it can't carry over to a later read-back. The latest reply decides.
5. `book_repair` takes only a shop. It refuses with `read_back_required` or `confirmation_required` unless that shop is prepared, read back, and confirmed, and books the stored estimate and time. Any outcome clears the confirmation, so another try needs another read-back.

A reply only counts if its speech started after a response finished playing following the read-back being handed to the model, tracked by conversation item. So "yes, Rockdale" said while picking a shop, or a passing "okay" said over the read-back, can't confirm it however late its transcript arrives. If the dispatcher talks over a read-back, it's discarded and the agent has to say it again. Limit changes use the same timing, without the check on what was said. `book_repair` waits up to five seconds for a reply still being transcribed, because the model can respond before transcription finishes.

The check looks for the details in what was said, not for an exact sentence, because a model may say "thirteen eighty" or give a breakdown. It accepts digit and spoken forms, and `prepare_booking` returns a `readBack` sentence for the agent to say so that it normally passes first time. A wrong price said alongside the right one would still pass, which the on-screen card makes visible.

The classifier is deliberately cautious and English only. Its worst mistake is treating a real yes as unclear, and then the agent asks again. A model that judged the reply was rejected, because that would be the same kind of decision the gate exists to check.

### Duplicates are blocked per truck

Each call creates its own issue, so `bookings.issue_id` being unique doesn't stop a second call booking the same breakdown. The repository also locks the truck and refuses a second booking for that truck, whatever the needed-by date, because a changed date on a later call is more likely the same breakdown than a new one. Tools return the existing booking marked `alreadyBooked`, so a retry, a second yes, and a new call all get a truthful answer. Nothing releases a booking in this draft, so a booked truck with a second real breakdown can't be booked until the mock data is reloaded.

### The failure switch sits in front of each shop

`ShopChecker` stands in for calling each shop's own system. The search asks every shop concurrently with a deadline, so one hanging shop only costs that deadline, and failures are returned in a new `unavailable` list rather than as `excluded`, because nothing is known about that shop. A timeout really waits, so the tool log shows it. `book_repair` asks the shop again before committing.

Faults are in memory, because they're a demo control and a restart clearing them is safe. They apply to voice tools only. `GET /issues` lists every issue, so a hanging shop there would stall the page.

### The tool log runs in the browser

The browser relays every call, so it can time the real round trip, including a request that never gets an answer. The log isn't stored. It sits in a panel beside the page, so it stays visible while the rest of the page scrolls.

### Spoken places use a small lookup

`update_issue` takes a place as text, and the server matches it against known mock places. An unmatched place returns `location_unknown`, and the agent asks again. The model never supplies coordinates.

### `contact` is no longer required

The brief expects the agent to ask only for what's missing, and nothing in a mock booking uses a callback number. `Issue.missing_details()` stops requiring `contact`, which is still accepted and stored. `symptoms` stays required, because the agent can fill it from the dispatcher's opening words without asking.

### The screen uses tool results

Issue and booking cards come from tool results, so the screen can't show a booking that a transcript merely mentions.

## Risks / Trade-offs

- [The browser relays the transcript, so a modified browser could post a false yes] → This is acceptable without authentication. A sideband connection would close it, and only the transport would change.
- [A background voice saying "yes" could count as the reply] → The card and read-back make a mistake visible. The booking is mock data.
- [A correct yes in other words or another language isn't recognized] → The agent asks again.
- [Straight-line distance understates road miles] → This is inherited from `add-issue-triage`.
- [Seeded start times can pass during a long demo] → Seeded times are relative to when the data is loaded, so reseed before a demo.

## Migration Plan

1. Finish `add-issue-triage`, then run `uv run alembic upgrade head` and reseed. Migration `0005` adds `booking_confirmations`.
2. Add `OPENAI_API_KEY` to `.env`.

To roll back, remove the `/voice` router and the voice UI, and downgrade to `0004`.

## Open Questions

- Should the agent reject a shop whose start time has already passed? Seeded times start ahead of the load time, so this draft doesn't check, and a demo should reseed first.
