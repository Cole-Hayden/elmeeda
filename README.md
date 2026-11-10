# Voice Booking Agent

A browser voice agent that handles a truck breakdown. A fleet dispatcher describes the problem, and the agent asks only for what's missing, compares fictional repair shops, gets a clear yes, books the repair, and stays truthful when a shop fails. It uses OpenAI's Realtime API for speech in and out, a Python backend for the shops and bookings, and Postgres for storage. Every truck, shop, price, and booking is mock data.

Requires [uv](https://docs.astral.sh/uv/), Docker, Node.js, and an OpenAI API key for voice.

Here's a link of me going through the code and explaining different aspects of it, https://www.loom.com/share/6a22892fcb2a4de8ba29c5faebb1f010

## How it works

The model only talks. Code decides prices, which shops qualify, and whether a booking is allowed.

```
Browser: OpenAI Realtime over WebRTC
   │  the model's tool calls, and transcripts of what was said
   ▼
Voice layer: api/voice.py, application/voice_tools.py
   • the tools update_issue, search_shops, prepare_booking, and book_repair
   • the confirmation gate: an exact read-back and a clear yes before any booking
   • the failure switch, which stands in for each shop's own system
   │  plain Python calls
   ▼
IssueService       stores what's known and reports what's missing
TriageService      picks the job, quotes each shop, and applies the vendor rules
BookingService     books in one locked transaction and takes a bay
   │
   ▼
Postgres: issues, trucks, shops, bookings
```

The voice layer doesn't repeat any business rules. Each tool calls the services underneath, so the tests can check triage and booking without a call.

## Run it

```bash
cp .env.example .env
```

Add your `OPENAI_API_KEY` to `.env`. Without it, everything works except starting a call, which returns `503`.

```bash
docker compose up -d --wait
```

```bash
uv run alembic upgrade head
```

```bash
uv run uvicorn issue_tracker.main:create_app --factory --port 8001
```

In another terminal, start the frontend. Its dev server sends `/api` requests to the backend on port 8001.

```bash
cd frontend && npm install && npm run dev
```

### Load the mock data

This loads the fictional trucks, the three repair shops, and the Truck 214 scenario. Run it just before a demo, because each shop's start time is set relative to the time it's loaded. Run it again between demos, since a truck can only be booked once. It deletes all bookings, trucks, shops, jobs, and any issue attached to a truck.

```bash
uv run python -m issue_tracker.infrastructure.seed
```

## Talk to the voice agent

Open http://localhost:5173 in your own browser, select **Start call**, and allow the microphone. The built-in browser in the Claude desktop app blocks microphones. The API key stays on the server.

Try the scenario: "Truck 214 is down on I-55 near Joliet with a coolant leak. I need a shop that can take it today, within 30 miles, under $1,500. What can you set up?"

The page shows:

- **Shops:** the options from the latest search, plus any excluded or unavailable shop and why.
- **Waiting for your yes:** the exact shop, estimate, and start time being read back. Nothing is booked yet.
- **Booked:** the booking ID, shop, estimate, and start time, which the agent reads aloud.
- **Tool call log:** in the panel on the right, each call's arguments, result or error, and duration.
- **Demo controls:** the failure switch.
- **Booked repairs:** every booking, newest first.

### Safety rules, enforced by the backend

- **Read-back:** `book_repair` refuses with `read_back_required` until the agent has said the prepared shop, estimate, and start time and that audio has finished playing. When it finishes, the browser sends the transcript of what the agent said to `POST /voice/calls/<issueId>/read-backs`, which the model can't call. Speech that starts earlier doesn't count as a reply, and a read-back the dispatcher talks over doesn't count either.
- **Confirmation:** `book_repair` then refuses with `confirmation_required` until the dispatcher's own reply to that read-back is a clear yes, such as "yes", "go ahead", or a short "okay". Anything with a negative word in it isn't. The browser sends that reply's transcript to `POST /voice/calls/<issueId>/answers`, which the model can't call either. The latest reply decides, and the booked price and time are the ones read back.
- **Duplicates:** a booked truck can't be booked again, whatever the date. A retry, a second yes, or a new call gets the existing booking, marked `alreadyBooked`, and no bay is taken. Nothing releases a booking yet, so reload the mock data to book that truck again.
- **Limits:** raising a budget, distance, or date the dispatcher already gave isn't saved until they say yes to it.
- **Failures:** the **Failure switch**, under **Demo controls**, makes one shop time out, return an error, or have no open bay, immediately and during a call. It clears when the backend restarts. A shop that gave no answer is listed in `unavailable`, not `excluded`, and the agent says what happened without guessing its price or bays.

The gate protects against the model, not against someone calling the backend directly. There's no authentication, and the backend trusts the browser to report transcripts honestly.

### Run the tools without a call

```bash
curl -i -X POST http://127.0.0.1:8001/voice/calls/<issueId>/tools/update_issue -H 'Content-Type: application/json' -d '{"place": "I-55 near Joliet"}'
```

The tools are `update_issue`, `search_shops`, `prepare_booking`, and `book_repair`. A failure the agent should explain, such as `no_open_bay` or `shop_timeout`, returns status `200` with an `error` field.

## Stretch goals

- **Change of mind:** when the dispatcher changes one constraint, such as the budget or the distance, `update_issue` saves only that field and keeps the rest, and the next search uses it. A tighter limit applies straight away. A looser one waits for the dispatcher's yes, so the agent can't relax a limit on its own. Run 6 of the [voice test script](scripts/voice_test_script.md) checks this on a call.
- **Interruptions:** the dispatcher can cut the agent off at any point, including while a tool call is running. A cut-off reply stops at once and its tool calls never run. A tool that's already running finishes once, and its result still reaches the agent and the tool call log. A read-back the dispatcher talks over doesn't count, so a "yes" said over it books nothing. Replies are sent to the backend in order, so the latest one decides. Run 7 of the [voice test script](scripts/voice_test_script.md) checks each of these on a call.
- **Feature of choice: a callback finds the existing booking.** If anyone calls back about a truck that's already booked, on any day, the agent reads back that booking instead of offering shops, because a dispatcher who calls twice, or two dispatchers working the same breakdown, shouldn't send one truck to two shops.

## Test

Postgres must be running. Integration tests recreate a separate `issue_tracker_test` database each run, so your development data isn't touched. The confirmation gate and duplicate protection tests are in `tests/integration/test_voice_tools.py` and `tests/integration/test_booking_storage.py`.

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run mypy
```

```bash
cd frontend && node --test src/*.test.js && npm run lint
```

### Check every requirement

Start the backend with the [dev-only issue routes](#dev-only-issue-routes) turned on:

```bash
ENABLE_DEV_API=true uv run uvicorn issue_tracker.main:create_app --factory --port 8001
```

Then run the check. It runs every suite above, then drives the Truck 214 scenario through the backend to check the flow, the confirmation gate, duplicate protection, the failure switch, and recovery. It reloads the mock data first, so it asks before deleting your bookings.

```bash
uv run python scripts/check_requirements.py
```

Then follow [scripts/voice_test_script.md](scripts/voice_test_script.md) for what only a real call can show: speech, the agent's wording, interruptions, and the screen.

## Dev-only issue routes

With `ENABLE_DEV_API=true`, the backend also serves `POST /issues` and `GET /issues/<issueId>`, hidden from the API docs. The tests and the requirements check use them to set up a breakdown without a call. They can't change, list, or book an issue, so every change goes through the voice tools and their rules.

## Check the database

Postgres listens on `127.0.0.1:5434`.

```bash
docker compose exec db psql -U issue_tracker -d issue_tracker -c 'SELECT * FROM bookings;'
```

## Project layout

Dependencies point inward, so the domain knows nothing about HTTP or SQL.

| Path | Responsibility |
| --- | --- |
| `src/issue_tracker/api/` | The voice routes in `voice.py`, the dev-only issue routes in `issues.py`, and their shared `schemas.py` and `dependencies.py` |
| `src/issue_tracker/application/` | Use cases, triage, the voice tools and agent instructions, the failure switch, and the repository interfaces |
| `src/issue_tracker/domain/` | The `Issue`, `Truck`, `Job`, `MaintenanceShop`, and `Booking` entities, plus job selection, quote, vendor, read-back, and confirmation rules |
| `src/issue_tracker/infrastructure/` | SQLAlchemy models, repository implementations, the OpenAI Realtime client, and fictional mock data |
| `src/issue_tracker/main.py` | App factory that wires the layers together |
| `frontend/` | React UI: the call, the tool relay and log, and the failure switch |
| `scripts/` | The requirements check and the voice test script |
| `migrations/` | Alembic schema migrations |
| `openspec/` | Specs and change proposals |
