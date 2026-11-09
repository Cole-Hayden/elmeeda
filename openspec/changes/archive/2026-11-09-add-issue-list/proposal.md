# Proposal

## Why

Opening the page creates an issue, so every visit adds an empty one and nobody can see the issues that already exist. Dispatchers need to see the issues and choose when to create one.

## What Changes

- Add `GET /issues`, which returns the latest 50 issues, newest first, in the same shape as `GET /issues/{id}`.
- Record when each issue was created, so the list has an order.
- Opening the page no longer creates an issue. Issues come from voice calls or `POST /issues`.
- The frontend shows the saved issues.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `issue-management`: Adds listing issues.

## Impact

- Adds migration `0004`, which existing environments must apply.
- Each listed issue is triaged live, so a list request costs up to 50 triage runs.
- The list doesn't refresh itself, so an issue created by a voice call appears after a reload.
