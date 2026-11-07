# Proposal

## Why

`POST /issues` stores what it is given and returns an ID, so nothing decides what repair a truck needs or who can do it. Shops have one flat estimate per problem, which can't express labor hours, parts, or a vendor that only does certain work. `drivable` is collected but changes nothing, so a truck that can't move can be offered a shop it can't reach. These decisions must come from data and rules, because a voice agent must not invent parts, hours, prices, or vendor eligibility.

## What Changes

- Validate issues at two levels: malformed values are rejected, while missing details return what still has to be asked.
- Add `symptoms`, `contact`, `loaded`, `hazmat`, `odometerMiles`, and `faultCodes` to issue details, and an optional `Idempotency-Key` header.
- Add `unknown` as a `problem`, which leads to a diagnostic job instead of a rejection.
- **BREAKING**: `POST /issues` returns the issue's triage result, not only `issueId`.
- Add `PATCH /issues/{issueId}` and `GET /issues/{issueId}`, both returning the triage result.
- Add a job catalog of labor hours and parts, selected by problem and truck.
- Add vendor capabilities: which jobs a shop does, at what labor rate, and for which makes, plus its tow service.
- **BREAKING**: Replace `shop_estimates` with calculated quotes. Booking compares against the calculated quote.
- Filter vendors with deterministic rules, and report why each excluded vendor was excluded.

## Capabilities

### New Capabilities

- `issue-triage`: Completeness checks, triage status, and job selection.
- `vendor-matching`: Vendor capabilities, filtering, quotes, and exclusion reasons.

### Modified Capabilities

- `issue-management`: New issue details, a new `POST` response, idempotent creation, and reading and updating issues.

## Impact

- **Code**: Domain, application, infrastructure, and API layers; mock data and seed; existing tests that assert the old response or flat estimates; the React UI's issue request.
- **APIs**: Changed `POST /issues` response; new `GET` and `PATCH /issues/{issueId}`. The `issueId` field keeps its name and meaning, so the current UI continues to work.
- **Database**: Migration `0003` adds issue and truck columns and the `jobs`, `job_parts`, and `vendor_capabilities` tables, adds tow columns to shops, and drops `shop_estimates`.
- **Dependencies**: None.
- **Ordering**: `add-issue-creation` must be archived first, because this change modifies its requirements.
