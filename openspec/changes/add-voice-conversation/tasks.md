# Tasks

## 1. Call setup

- [ ] 1.1 Add optional voice settings and make `httpx` a runtime dependency, and verify the app and tests still start without a key
- [ ] 1.2 Add the Realtime gateway, instructions, and tool schemas, and verify the request sent to OpenAI and its error handling with unit tests
- [ ] 1.3 Add `POST /voice/calls` and register the router after `add-issue-triage` is finished, and verify each scenario with integration tests

## 2. Browser

- [ ] 2.1 Add the `useRealtimeCall` hook, and verify a real call connects from the browser with speech in and speech out
- [ ] 2.2 Add the confirmation gate as a pure function, and verify every booking scenario in the spec

## 3. Tools

- [ ] 3.1 Add known places and place lookup, and verify known and unknown places with unit tests
- [ ] 3.2 Add the tool route, with `update_issue`, `search_shops`, `prepare_booking`, and `book_repair`, and verify each with integration tests, including booking rejections

## 4. Screen

- [ ] 4.1 Add the call controls, transcript, and issue, confirmation, and booking cards, using tool results for state, and verify them in the browser

## 5. Verification

- [ ] 5.1 Run the Truck 214 scenario by voice, from request to booking, and verify the booking with `psql`
- [ ] 5.2 Run the shop failure scenario by setting Rockdale's open bays to 0 after it's offered, and verify the agent reports the failure and moves on truthfully
- [ ] 5.3 Update `README.md`, and verify `pytest`, `ruff check`, `mypy`, `npm run lint`, and `openspec validate add-voice-conversation --strict` pass
