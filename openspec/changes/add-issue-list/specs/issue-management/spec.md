## ADDED Requirements

### Requirement: List issues
The system SHALL expose `GET /issues`, which responds with status 200 and a JSON array of the latest 50 issues, newest first. Each item SHALL have the same shape as the `GET /issues/{id}` response.

#### Scenario: Newest issue is first
- **WHEN** a client creates two issues and then sends `GET /issues`
- **THEN** the response status is 200
- **AND** the second issue is listed before the first

#### Scenario: More issues exist than the limit
- **WHEN** more than 50 issues exist and a client sends `GET /issues`
- **THEN** the response contains only the 50 newest issues

#### Scenario: Database is unavailable
- **WHEN** a client sends `GET /issues` while the database cannot be reached
- **THEN** the response status is 503
- **AND** the response body contains a generic error message without connection details
