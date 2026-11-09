# Tasks

## 1. Call setup

- [x] 1.1 Add optional voice settings and make `httpx` a runtime dependency, and verify the app and tests still start without a key
- [x] 1.2 Add the Realtime gateway, instructions, and tool schemas, and verify the request sent to OpenAI and its error handling with unit tests
- [x] 1.3 Add `POST /voice/calls` and register the router after `add-issue-triage` is finished, and verify each scenario with integration tests

## 2. Browser

- [x] 2.1 Add the `useRealtimeCall` hook, and verify a real call connects from the browser with speech in and speech out
- [x] 2.2 Add the confirmation gate in the backend, with the browser relaying replies, and verify every booking scenario in the spec

## 3. Tools

- [x] 3.1 Add known places and place lookup, and verify known and unknown places with unit tests
- [x] 3.2 Add the tool route, with `update_issue`, `search_shops`, `prepare_booking`, and `book_repair`, and verify each with integration tests, including booking rejections

## 4. Screen

- [x] 4.1 Add the call controls, transcript, and issue, confirmation, and booking cards, using tool results for state, and verify them in the browser

- [x] 4.2 Add the tool call log and failure switch, and verify them in the browser with a simulated call

- [x] 4.3 Take the transcript off the screen, keeping the transcripts the confirmation check relies on

- [x] 4.4 Move the tool call log to a panel on the right, and verify it in the browser with a simulated call

- [x] 4.5 Replace the issue list on the page with booked repairs that reload after a booking, and verify in the browser with a simulated call

## 5. Duplicates and failures

- [x] 5.1 Block a second booking for one truck, whatever the date, return existing bookings to retries and new calls, and verify with integration tests
- [x] 5.2 Add per-shop timeout, error, and no-open-bay failures to search and booking, and verify with integration tests
- [x] 5.3 Require a spoken yes before loosening a limit, report `shops_unavailable` when a shop's silence leaves nothing to offer, add prompt recovery for `quote_changed`, and verify with tests
- [x] 5.4 Require the agent to finish saying the prepared shop, estimate, and start time before a yes counts, and verify with tests

## 6. Verification

- [x] 6.1 Run the Truck 214 scenario by voice, from request to booking, and verify the booking with `psql`
- [x] 6.2 Run the shop failure scenario with the failure switch during a call, and verify the agent reports the failure and moves on truthfully
- [x] 6.3 Update `README.md`, and verify `pytest`, `ruff check`, `mypy`, `npm run lint`, and `openspec validate add-voice-conversation --strict` pass

## 7. Stretch goals

- [x] 7.1 Change one limit by voice while keeping every other detail, and verify with integration tests that `update_issue` changes only the fields it was sent
- [x] 7.2 Name the callback that finds an existing booking as the chosen feature, with a sentence on why, in `README.md`
- [x] 7.3 Run Run 7 of `scripts/voice_test_script.md` on a live call, cutting the agent off mid-sentence, during a running tool call, and during the read-back, and verify every interruption scenario in the spec
