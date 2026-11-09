# Proposal

## Why

Dispatchers create and change issues by voice, and nothing in the frontend calls `/issues` any more. Two of its routes weakened rules the voice agent depends on. `PATCH /issues/{issueId}` changed an issue without the limit-change confirmation that `update_issue` applies, so a direct caller could raise a budget with no yes. `GET /issues` listed every recent issue ID, and an issue ID is the only thing that stops someone posting a fake read-back or yes to a call.

## What Changes

- Remove `PATCH /issues/{issueId}`. Changing an issue goes through the voice `update_issue` tool.
- Remove `GET /issues`, the issue list. The page lists booked repairs from `GET /voice/bookings`.
- Keep `POST /issues` and `GET /issues/{issueId}` for tests and `scripts/check_requirements.py`, mounted only when the `ENABLE_DEV_API` setting is on and hidden from the API docs.
- Move the request and response models, dependencies, and HTTP errors that the voice routes share with the issue routes into `api/schemas.py` and `api/dependencies.py`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `issue-management`: Creating and reading an issue become dev-only, and updating and listing issues are removed.

## Impact

- **APIs**: `PATCH /issues/{issueId}` and `GET /issues` are removed. `POST /issues` and `GET /issues/{issueId}` return 404 unless `ENABLE_DEV_API` is on.
- **Configuration**: New `ENABLE_DEV_API` setting, off by default.
- **Database**: None. The `created_at` column from `add-issue-list` still orders booked repairs.
- **Ordering**: Archive after `add-issue-triage` and `add-issue-list`, whose requirements this changes.
