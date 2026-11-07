# Spec Delta

## MODIFIED Requirements

### Requirement: Create an issue
The system SHALL expose `POST /issues`, which needs no request body, creates one issue, and responds with status 201 and the issue's triage result, including its `issueId`.

#### Scenario: Issue is created
- **WHEN** a client sends `POST /issues` with no request body
- **THEN** the response status is 201
- **AND** the response body contains a UUID `issueId`
- **AND** the response body has `status` set to `needs_info`

### Requirement: Create an issue with breakdown details
`POST /issues` SHALL accept an optional JSON body with any of `truckUnitNumber`, `problem`, `location` (`description`, `latitude`, `longitude`), `drivable`, `neededBy`, `maxDistanceMiles`, `maxBudget`, `symptoms`, `contact` (`name`, `phone`), `loaded`, `hazmat`, `odometerMiles`, and `faultCodes` (a list of `spn` and `fmi`), and SHALL store every detail it receives with the issue.

#### Scenario: Details are stored
- **WHEN** a client sends `POST /issues` with valid details
- **THEN** the response status is 201
- **AND** the stored issue holds those details

#### Scenario: Only some details are known
- **WHEN** a client sends `POST /issues` with only some details
- **THEN** the response status is 201
- **AND** the details that were not sent remain unset on the stored issue

#### Scenario: Truck does not exist
- **WHEN** a client sends a `truckUnitNumber` that matches no truck
- **THEN** the response status is 422
- **AND** no issue is stored

#### Scenario: Details are invalid
- **WHEN** a client sends a detail that fails validation, such as an unlisted `problem`, a negative `maxBudget`, a negative `odometerMiles`, or an `fmi` above 31
- **THEN** the response status is 422
- **AND** no issue is stored

#### Scenario: Needed-by date has passed
- **WHEN** a client sends a `neededBy` date earlier than today in Central time
- **THEN** the response status is 422
- **AND** no issue is stored

## ADDED Requirements

### Requirement: Creating an issue can be retried safely
`POST /issues` SHALL accept an optional `Idempotency-Key` header. Requests with the same key SHALL refer to one issue.

#### Scenario: Request is retried with the same key
- **WHEN** a client sends `POST /issues` twice with the same `Idempotency-Key`
- **THEN** the first response status is 201
- **AND** the second response status is 200 with the same `issueId`
- **AND** the database contains one issue for that key

#### Scenario: Requests run concurrently with the same key
- **WHEN** two `POST /issues` requests with the same `Idempotency-Key` run at the same time
- **THEN** both responses contain the same `issueId`
- **AND** the database contains one issue for that key

#### Scenario: Retry has a different body
- **WHEN** a client repeats an `Idempotency-Key` with a different body
- **THEN** the response status is 200 with the original issue's details

### Requirement: Read an issue
The system SHALL expose `GET /issues/{issueId}`, which responds with the issue's current triage result.

#### Scenario: Issue exists
- **WHEN** a client sends `GET /issues/{issueId}` for an existing issue
- **THEN** the response status is 200
- **AND** the response body contains the issue's stored details and current triage result

#### Scenario: Issue does not exist
- **WHEN** a client sends `GET /issues/{issueId}` for an unknown ID
- **THEN** the response status is 404

### Requirement: Update an issue's details
The system SHALL expose `PATCH /issues/{issueId}`, which accepts the same details as `POST /issues`, changes only the details that were sent with a value, and responds with the updated triage result.

#### Scenario: Detail is added
- **WHEN** a client sends `PATCH /issues/{issueId}` with `drivable`
- **THEN** the response status is 200
- **AND** the stored issue has that value
- **AND** its other details are unchanged

#### Scenario: Detail is sent as null
- **WHEN** a client sends `PATCH /issues/{issueId}` with a detail set to null
- **THEN** the response status is 200
- **AND** that stored detail is unchanged

#### Scenario: Update is invalid
- **WHEN** a client sends `PATCH /issues/{issueId}` with an invalid detail or an unknown truck
- **THEN** the response status is 422
- **AND** the stored issue is unchanged

#### Scenario: Issue does not exist
- **WHEN** a client sends `PATCH /issues/{issueId}` for an unknown ID
- **THEN** the response status is 404

#### Scenario: Issue is already booked
- **WHEN** a client sends `PATCH /issues/{issueId}` for an issue that has a booking
- **THEN** the response status is 409
- **AND** the stored issue is unchanged
