# Tasks

## 1. Prerequisites

- [x] 1.1 Archive `add-issue-creation`, and verify `openspec/specs/issue-management/spec.md` exists
- [x] 1.2 Inject a clock using Central time, make `SCENARIO_DAY` the current date, replace literal scenario dates in tests, and verify `pytest` still passes

## 2. Domain

- [x] 2.1 Add `unknown` to `ProblemType`, add `Job`, `JobPart`, and `VendorCapability`, and add new details and tow rules to `Issue`, and verify with unit tests for `missing_details` and tow rules
- [x] 2.2 Add job selection as a pure function, and verify the specific, make, and generic order with unit tests
- [x] 2.3 Add the quote calculation as a pure function, and verify all seven seeded estimates, the three tow estimates, and rounding with unit tests
- [x] 2.4 Add vendor filtering as a pure function, and verify every reason, the rule order, the budget boundary, and option sorting with unit tests

## 3. Database

- [x] 3.1 Add migration `0003` and matching models, and verify `alembic upgrade head`, `alembic downgrade 0002`, and `alembic upgrade head` run cleanly
- [x] 3.2 Add fictional jobs, parts, capabilities, tow fees, VINs, and engines to the mock data and seed, and verify the scenario tests in `tests/unit/test_mock_data.py` still describe the same tradeoffs
- [x] 3.3 Add repository methods for jobs and for loading shops with capabilities, translating storage errors, and verify with integration tests
- [x] 3.4 Add idempotent creation and the locked detail update to the issue repository, and verify concurrent creation and an update racing a booking with integration tests

## 4. Booking

- [x] 4.1 Change the booking repository to compare against the calculated quote and add the `job_not_offered` rejection, and verify every booking scenario in the spec with `tests/integration/test_booking_storage.py`

## 5. Triage and API

- [x] 5.1 Add `TriageService`, and verify each status with unit tests using fake repositories
- [x] 5.2 Extend request validation with the new details and the `neededBy` rule, and verify every invalid case returns 422 and saves nothing
- [x] 5.3 Change `POST /issues` to return the triage result and honor `Idempotency-Key`, and update `tests/integration/test_create_issue.py` and `tests/integration/test_create_issue_details.py`
- [x] 5.4 Add `GET` and `PATCH /issues/{issueId}`, and add integration tests for every scenario in the spec
- [x] 5.5 Add integration tests for both Truck 214 scenario outcomes through the API

## 6. Frontend

- [x] 6.1 Send one `Idempotency-Key` per page load and remove the StrictMode guard, and verify in the browser that loading the page creates one issue and that retrying after a failure creates one issue

## 7. Documentation and end-to-end check

- [x] 7.1 Update `README.md` with the new request, response, and endpoints, and verify the documented commands run as written
- [x] 7.2 Reseed, run the server, and use `curl` to create a partial Truck 214 issue, `PATCH` it until `options_ready`, and read it with `GET`, and verify the results with `psql`
- [x] 7.3 Verify `pytest`, `ruff check`, `mypy`, `npm run lint`, and `openspec validate add-issue-triage --strict` pass

## Workflow follow-up

- Archive the change with `openspec archive add-issue-triage` after review.
