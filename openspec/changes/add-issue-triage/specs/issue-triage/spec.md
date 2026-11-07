# Spec Delta

## Purpose

Works out what is still missing from an issue, what job it needs, and what state it is in. Results come from stored data and fixed rules, not from a model.

## ADDED Requirements

### Requirement: Report missing details
The triage result SHALL list in `missingDetails` every detail still needed to plan a repair. `truckUnitNumber`, `problem`, `location`, `drivable`, `neededBy`, `maxDistanceMiles`, `maxBudget`, and `symptoms` SHALL always be needed. `loaded` and `hazmat` SHALL be needed only when the truck needs a tow. `contact`, `odometerMiles`, and `faultCodes` SHALL never be needed.

#### Scenario: Details are missing
- **WHEN** an issue has no `drivable` value
- **THEN** `missingDetails` includes `drivable`
- **AND** `status` is `needs_info`

#### Scenario: False counts as answered
- **WHEN** an issue has `drivable` set to false
- **THEN** `missingDetails` does not include `drivable`

#### Scenario: Drivable truck needs no tow details
- **WHEN** an issue has `drivable` set to true and `problem` set to `coolant_leak`
- **THEN** `missingDetails` includes neither `loaded` nor `hazmat`

#### Scenario: Optional details are absent
- **WHEN** an issue has no `odometerMiles` or `faultCodes`
- **THEN** `missingDetails` includes neither of them

### Requirement: Determine whether a tow is needed
The triage result SHALL set `towRequired` to true when `drivable` is false or `problem` is `brake_failure`.

#### Scenario: Truck can't be driven
- **WHEN** an issue has `drivable` set to false
- **THEN** `towRequired` is true

#### Scenario: Driver reports failed brakes on a drivable truck
- **WHEN** an issue has `problem` set to `brake_failure` and `drivable` set to true
- **THEN** `towRequired` is true

#### Scenario: Truck can be driven
- **WHEN** an issue has `problem` set to `coolant_leak` and `drivable` set to true
- **THEN** `towRequired` is false

### Requirement: Report triage status
The triage result SHALL report `status` as `booked` when the issue has a booking, `needs_info` when details are missing, `options_ready` when at least one vendor qualifies, and otherwise `no_vendor`. Status SHALL be calculated from current data on every response.

#### Scenario: A vendor qualifies
- **WHEN** an issue has every needed detail and at least one vendor qualifies
- **THEN** `status` is `options_ready`

#### Scenario: No vendor qualifies
- **WHEN** an issue has every needed detail and no vendor qualifies
- **THEN** `status` is `no_vendor`

#### Scenario: Availability changes
- **WHEN** the only qualifying vendor loses its last open bay after an issue is created
- **THEN** the next `GET /issues/{issueId}` reports `status` as `no_vendor`

#### Scenario: Issue is booked
- **WHEN** an issue has a booking
- **THEN** `status` is `booked`
- **AND** `options` is empty

### Requirement: Select a job from the catalog
The system SHALL select a job when the issue has a `problem` and a truck, choosing the most specific catalog row that matches: make and engine, then make, then generic. The triage result SHALL include the job's code, name, labor hours, parts, and whether it requires diagnosis.

#### Scenario: Generic job applies
- **WHEN** an issue's problem has only a generic job
- **THEN** the result's `job` is that generic job with its labor hours and parts

#### Scenario: Specific job applies
- **WHEN** a job exists for the issue's problem and the truck's make, alongside a generic job
- **THEN** the result's `job` is the make-specific job

#### Scenario: Job can't be determined yet
- **WHEN** an issue has no `problem` or no truck
- **THEN** the result's `job` is null

### Requirement: Route unrecognized problems to diagnosis
The system SHALL accept `unknown` as a `problem` and SHALL select a diagnostic job for it, which has no parts and has `requiresDiagnosis` set to true.

#### Scenario: Problem doesn't fit a known type
- **WHEN** an issue has `problem` set to `unknown` and a truck
- **THEN** the response is not a rejection
- **AND** the result's `job` has `requiresDiagnosis` set to true
- **AND** the job has no parts
