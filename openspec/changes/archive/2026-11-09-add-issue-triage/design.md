# Design

## Context

See `proposal.md` for motivation and the spec deltas for required behavior. Issues are filled in over a conversation, so partial data is normal. All trucks, shops, jobs, and prices are fictional mock data. Trucking has standards for repair coding (VMRS), labor times (Standard Repair Times), and fault codes (J1939 SPN and FMI). Research for this change found no published standard for vendor selection, so those rules are this project's own design.

## Goals / Non-Goals

**Goals:**

- Make every job, price, and vendor decision deterministic and testable without a model.
- Let a client explain why a vendor was or wasn't offered, using the server's reasons.
- Keep the Truck 214 scenario's estimates and tradeoffs unchanged.

**Non-Goals:**

- Voice integration. It will call these endpoints in a later change.
- Turning a spoken location into coordinates. `location` still requires latitude and longitude, so the voice change must solve this.
- Mobile repair. A truck that can't be driven needs a tow in this change.
- Choosing jobs or urgency from fault codes. They are stored for the vendor and for later rules.
- Warranty and maintenance rules based on `odometerMiles`.
- A licensed labor guide, parts catalog, or real VMRS codes.
- Authentication and authorization.

## Decisions

### Triage runs inside the request

The pipeline is a few database reads and pure functions, so a queue would add failure modes and no benefit.

```text
Validate shape → Save → Check completeness → Select job → Filter vendors and quote → Respond
```

`TriageService` in the application layer orchestrates this. The selection, filtering, and pricing rules are pure domain functions.

### Two levels of validation

| Outcome | When | Response |
| --- | --- | --- |
| Rejected | Malformed value, unlisted `problem`, unknown truck, or `neededBy` in the past | `422`, nothing saved |
| Accepted | Details missing | Saved, `status: needs_info`, with `missingDetails` |
| Accepted | No vendor qualifies | Saved, `status: no_vendor`, with reasons |

A low budget isn't invalid input. It's a result that a dispatcher can act on.

### Status and options are calculated on every read

Prices, bays, and start times change, so storing them on the issue would create stale copies. `needs_info`, `options_ready`, and `no_vendor` are calculated. `booked` is calculated from the existence of a booking. A booked issue returns no options.

### Required details depend on the issue

`Issue.missing_details()` gains `symptoms`. It also asks for `loaded` and `hazmat` when the truck needs a tow. Other fields keep their current meaning, and `contact`, `odometerMiles`, and `faultCodes` are never required.

A truck needs a tow when `drivable` is false or `problem` is `brake_failure`. The brake rule applies whatever the driver says, because driving with failed brakes isn't a safe option to offer. `drivable` is still required for every issue.

### One job row per truck variant

`jobs` has `job_code`, `problem`, nullable `make` and `engine`, `name`, `labor_hours`, `requires_diagnosis`, and nullable `vmrs_code`. `job_parts` has `job_code`, `part_number`, `description`, `quantity`, and `unit_price`.

The most specific row wins: make and engine, then make, then generic. Each problem has a generic row, and `(problem, make, engine)` is unique with `NULLS NOT DISTINCT`. A separate applicability table was rejected, because labor and parts differ by variant, so a variant needs its own row anyway.

`problem: unknown` selects the diagnostic job, which has `requires_diagnosis` set and no parts. Its quote covers diagnosis only, and clients must say so. An unlisted `problem` value is still rejected. Rejecting `unknown` would fail any call about a problem outside the list.

`vmrs_code` is null in the mock data. Real codes need verifying, and their licensing needs checking before production use.

### Capabilities are per shop and job

`vendor_capabilities` has `shop_id`, `job_code`, `labor_rate`, and nullable `authorized_makes`, where null means any make. A shop with no row for a job can't be offered it. Tow service is a property of the shop: nullable `tow_base_fee` and `tow_per_mile`, which must be set together, and `tows_hazmat`.

`MaintenanceShop.estimates` is replaced by capabilities, and `shop_estimates` is dropped.

### Quotes are calculated by one pure function

```text
estimate = labor_hours × labor_rate + sum(quantity × unit_price) + tow
tow      = tow_base_fee + tow_per_mile × miles to the shop, when the truck needs a tow
```

The result is rounded to cents using half-up. Distance uses the existing straight-line `Location.miles_to`.

Booking calls the same function inside its existing transaction, and raises `QUOTE_CHANGED` if the result or start time differs from what was agreed, or if the shop can no longer provide a required tow. It raises `JOB_NOT_OFFERED` if the shop no longer does the job or doesn't work on the truck's make. Sharing the function means the offered price and the booked price can't drift apart. Distance and budget limits aren't rechecked, so a dispatcher can still knowingly agree to go over them. `Booking` and its contract are otherwise unchanged.

### Vendors are filtered in a fixed order

Every shop gets either an option or the first reason it fails. The order is cheapest to explain first, and capacity last, so the reason given is the most lasting one.

| Order | Rule | Reason |
| --- | --- | --- |
| 1 | Has a capability for the job | `job_not_offered` |
| 2 | Works on the truck's make | `make_not_supported` |
| 3 | Tows, if a tow is needed | `no_tow_service` |
| 4 | Tows hazmat, if a tow is needed and `hazmat` is true | `hazmat_not_supported` |
| 5 | Within `maxDistanceMiles` | `too_far` |
| 6 | Estimate is at or below `maxBudget` | `over_budget` |
| 7 | Has an open bay | `no_open_bay` |
| 8 | `earliest_start` is on or before `neededBy` | `starts_too_late` |

Options are sorted by earliest start, then estimate, then shop name. The agent explains the tradeoffs, so the order isn't a recommendation.

### Mock data reproduces today's estimates

These values reproduce every current estimate exactly. This was checked against `mock_data.py` when drafting.

| Job | Hours | Parts | Rockdale | Woodridge | Millrace |
| --- | --- | --- | --- | --- | --- |
| Coolant leak | 4.0 | $400 | $245/hr → $1,380 | $180/hr → $1,120 | $310/hr → $1,640 |
| Tire blowout | 1.0 | $400 | $240/hr → $640 | $180/hr → $580 | Not offered |
| Brake failure | 5.0 | $550 | Not offered | $180/hr → $1,450 | $235/hr → $1,725 |

All three shops seed a tow at $60 plus $4 per mile. For Truck 214's coolant leak with a tow, that gives Rockdale $1,457.19, Woodridge $1,257.09, and Millrace $1,751.34, so the scenario's budget outcome holds whether or not the truck can be driven.

To exercise the other rules, only Woodridge seeds `tows_hazmat`, Millrace is limited to Freightliner and Volvo, and all three offer the diagnostic job (2.0 hours, no parts) at their coolant-leak rate.

### PATCH merges and can't change a booked issue

Fields not sent, or sent as null, stay unchanged. Details can be corrected but not cleared, which avoids a second meaning for null. A new repository method applies the merge inside a transaction that locks the issue row first, then checks for a booking. Booking takes the same lock first, so an update and a booking can't interleave. A booked issue returns `409`.

### Idempotency is a unique issue column

`issues.idempotency_key` is nullable and unique. Creation uses `INSERT ... ON CONFLICT DO NOTHING` and then reads the row, so concurrent duplicates are safe. A replay returns `200` with the original issue, and its body is ignored.

The header is optional, because a request with no body and no header must keep working. The UI generates one key per page load, which replaces its StrictMode guard and makes its retries safe.

### Fault codes are stored as JSONB

They are only stored and returned, so a child table has no use yet. `spn` is limited to 0–524287 and `fmi` to 0–31.

### The clock is injected

`neededBy` validation depends on today's date in Central time, so `IssueService` takes a clock and tests can fix it. `SCENARIO_DAY` becomes the current Central date when the module loads, and tests use it instead of a literal date. Otherwise the suite and the demo would start failing the day after `2026-11-07`.

## Response

```json
{
  "issueId": "…",
  "status": "options_ready",
  "missingDetails": [],
  "truck": {"unitNumber": "214", "make": "Freightliner", "model": "Cascadia", "year": 2021, "vin": "…", "engine": "…"},
  "details": {"problem": "coolant_leak", "drivable": false},
  "towRequired": true,
  "job": {
    "jobCode": "COOLANT_LEAK_GENERIC",
    "name": "Coolant leak repair",
    "laborHours": "4.0",
    "requiresDiagnosis": false,
    "parts": [{"partNumber": "…", "description": "…", "quantity": 1, "unitPrice": "400.00"}]
  },
  "options": [{
    "shopId": "…",
    "name": "Woodridge Fleet Service",
    "distanceMiles": 19.3,
    "earliestStart": "2026-11-07T13:00:00-06:00",
    "estimate": "1257.09",
    "breakdown": {"labor": "720.00", "parts": "400.00", "tow": "137.09"}
  }],
  "excluded": [{"shopId": "…", "name": "Millrace Diesel Works", "reason": "over_budget"}]
}
```

`details` is abbreviated here and holds every stored detail. `truck` and `job` are null until they can be determined. `options` and `excluded` stay empty until the status is `options_ready` or `no_vendor`.

## Risks / Trade-offs

- [Every estimate before diagnosis can be wrong] → Prices are named `estimate`, `requiresDiagnosis` flags the riskiest case, and the real cause is left for a shop to find.
- [Straight-line distance understates road miles and tow cost] → This is acceptable for mock data. A routing service could replace it behind `miles_to`.
- [Filtering every shop in Python won't scale to a large network] → The mock data has three shops. A geographic pre-filter can be added in the repository when needed.
- [A replay with the same key and a different body silently returns the original] → This matches the purpose of the key. Corrections go through `PATCH`.
- [Showing every excluded shop could expose vendor details to a future customer-facing client] → The current clients are internal, and this can be restricted when authentication exists.
- [Dropping `shop_estimates` loses its data] → That table only holds mock data, and each booking stores its own estimate.

## Migration Plan

1. Archive `add-issue-creation`.
2. Run `uv run alembic upgrade head` to apply `0003`.
3. Run `uv run python -m issue_tracker.infrastructure.seed` to load jobs and capabilities.

Migration `0003` doesn't convert `shop_estimates` data, because the seed recreates it. To roll back, run `uv run alembic downgrade 0002` and reseed from the previous commit.

## Open Questions

- Should a dispatcher be able to override the brake failure tow rule? This draft says no.
- Should `maxBudget` apply to diagnostic jobs, given their quote doesn't include the repair? This draft applies it.
