# Spec Delta

## MODIFIED Requirements

### Requirement: Create an issue
When the `ENABLE_DEV_API` setting is on, the system SHALL expose `POST /issues`, which needs no request body, creates one issue, and responds with status 201 and the issue's triage result, including its `issueId`. When the setting is off, `POST /issues` SHALL return 404. The route SHALL NOT appear in the API docs.

#### Scenario: Issue is created
- **WHEN** the dev routes are on and a client sends `POST /issues` with no request body
- **THEN** the response status is 201
- **AND** the response body contains a UUID `issueId`
- **AND** the response body has `status` set to `needs_info`

#### Scenario: Dev routes are off
- **WHEN** `ENABLE_DEV_API` is off and a client sends `POST /issues`
- **THEN** the response status is 404
- **AND** no issue is stored

#### Scenario: API docs are read
- **WHEN** a client reads `/openapi.json`, whether or not the dev routes are on
- **THEN** no `/issues` path is listed

### Requirement: Read an issue
When the `ENABLE_DEV_API` setting is on, the system SHALL expose `GET /issues/{issueId}`, which responds with the issue's current triage result. When the setting is off, it SHALL return 404.

#### Scenario: Issue exists
- **WHEN** the dev routes are on and a client sends `GET /issues/{issueId}` for an existing issue
- **THEN** the response status is 200
- **AND** the response body contains the issue's stored details and current triage result

#### Scenario: Issue does not exist
- **WHEN** a client sends `GET /issues/{issueId}` for an unknown ID
- **THEN** the response status is 404

## REMOVED Requirements

### Requirement: Update an issue's details
**Reason**: It changed an issue without the limit-change confirmation the voice agent applies, so a direct caller could raise a limit with no yes, and nothing in the frontend used it.
**Migration**: Change an issue with the voice `update_issue` tool, through `POST /voice/calls/{issueId}/tools/update_issue`, which changes only the details it's sent.

### Requirement: List issues
**Reason**: It listed every recent issue ID, which is the only thing that stops someone posting a fake read-back or yes to a call. It also triaged up to 50 issues on each request, asking every shop each time, and the page no longer used it.
**Migration**: List booked repairs with `GET /voice/bookings`. Read one issue with `GET /issues/{issueId}` when the dev routes are on.
