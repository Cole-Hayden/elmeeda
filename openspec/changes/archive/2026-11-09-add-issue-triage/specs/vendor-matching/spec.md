# Spec Delta

## Purpose

Decides which vendors can take a job and what each would charge, using stored capabilities and fixed rules. Every vendor is either offered with a quote or excluded with a reason.

## ADDED Requirements

### Requirement: Evaluate every vendor against fixed rules
When an issue has every needed detail and isn't booked, the system SHALL place every vendor in `options` or in `excluded`. An excluded vendor SHALL have the reason for the first rule it fails, checked in this order: `job_not_offered`, `make_not_supported`, `no_tow_service`, `hazmat_not_supported`, `too_far`, `over_budget`, `no_open_bay`, `starts_too_late`.

#### Scenario: Vendor doesn't offer the job
- **WHEN** a vendor has no capability for the selected job
- **THEN** it is excluded with reason `job_not_offered`

#### Scenario: Vendor doesn't work on the make
- **WHEN** a vendor's capability lists authorized makes that don't include the truck's make
- **THEN** it is excluded with reason `make_not_supported`

#### Scenario: Vendor can't tow
- **WHEN** a tow is required and the vendor has no tow service
- **THEN** it is excluded with reason `no_tow_service`

#### Scenario: Vendor can't tow hazmat
- **WHEN** a tow is required, `hazmat` is true, and the vendor doesn't tow hazmat
- **THEN** it is excluded with reason `hazmat_not_supported`

#### Scenario: Vendor is too far
- **WHEN** a vendor is farther than `maxDistanceMiles` from the issue's location
- **THEN** it is excluded with reason `too_far`

#### Scenario: Vendor is over budget
- **WHEN** a vendor's estimate is above `maxBudget`
- **THEN** it is excluded with reason `over_budget`

#### Scenario: Estimate equals the budget
- **WHEN** a vendor's estimate equals `maxBudget`
- **THEN** it isn't excluded for budget

#### Scenario: Vendor has no open bay
- **WHEN** a vendor has no open bays
- **THEN** it is excluded with reason `no_open_bay`

#### Scenario: Vendor starts too late
- **WHEN** a vendor's earliest start is after `neededBy`
- **THEN** it is excluded with reason `starts_too_late`

#### Scenario: Vendor fails several rules
- **WHEN** a vendor is both too far and over budget
- **THEN** it is excluded with reason `too_far` only

### Requirement: Calculate quotes from the job and the vendor
The system SHALL calculate an estimate as the job's labor hours times the vendor's labor rate for that job, plus the job's parts, plus the vendor's tow fee when a tow is required. An option SHALL include the estimate and its `labor`, `parts`, and `tow` breakdown. The tow fee SHALL be the vendor's base fee plus its per-mile fee times the distance to the vendor. Amounts SHALL be rounded to cents.

#### Scenario: No tow is required
- **WHEN** the mock data's Truck 214 has a coolant leak, can be driven, and Woodridge Fleet Service is evaluated
- **THEN** the estimate is `1120.00`
- **AND** the breakdown's `tow` is `0.00`

#### Scenario: A tow is required
- **WHEN** the mock data's Truck 214 has a coolant leak, can't be driven, and Woodridge Fleet Service is evaluated
- **THEN** the estimate is `1257.09`
- **AND** the breakdown's `tow` is `137.09`

### Requirement: Keep the Truck 214 scenario's outcome
With the mock data, Truck 214's coolant leak SHALL offer Rockdale Junction Truck Care and Woodridge Fleet Service, and SHALL exclude Millrace Diesel Works as over budget, whether or not the truck can be driven.

#### Scenario: Truck can be driven
- **WHEN** the scenario issue has `drivable` set to true
- **THEN** `options` contains Rockdale and Woodridge
- **AND** `excluded` contains Millrace with reason `over_budget`

#### Scenario: Truck can't be driven
- **WHEN** the scenario issue has `drivable` set to false and `hazmat` set to false
- **THEN** `options` contains Rockdale and Woodridge
- **AND** `excluded` contains Millrace with reason `over_budget`

### Requirement: Report what the search checked
Each entry in `options` SHALL include the vendor's `openBays`, `distanceMiles`, `earliestStart`, and `estimate`.

#### Scenario: Vendor is offered
- **WHEN** a vendor qualifies for an issue
- **THEN** its option includes its current open bays, distance, earliest start, and estimate

### Requirement: Order options deterministically
The system SHALL sort `options` by earliest start, then estimate, then shop name.

#### Scenario: Vendors have different start times
- **WHEN** two vendors qualify with different earliest starts
- **THEN** the vendor that starts first is listed first

### Requirement: Booking uses the calculated quote
The system SHALL reject a booking with `quote_changed` when the agreed estimate or start time differs from the quote calculated at booking time or the vendor can't provide a required tow, and SHALL reject it with `job_not_offered` when the vendor has no capability for the job or doesn't work on the truck's make.

#### Scenario: Quote still matches
- **WHEN** a booking's agreed estimate and start time match the calculated quote
- **THEN** the booking is stored
- **AND** the shop has one fewer open bay

#### Scenario: Labor rate changed
- **WHEN** a vendor's labor rate changes after a quote was offered and the old estimate is booked
- **THEN** the booking is rejected with `quote_changed`
- **AND** the shop's open bays are unchanged

#### Scenario: Tow requirement changed
- **WHEN** the truck's `drivable` value changes after a quote was offered and the old estimate is booked
- **THEN** the booking is rejected with `quote_changed`

#### Scenario: Capability was removed
- **WHEN** a vendor's capability for the job is removed after a quote was offered
- **THEN** the booking is rejected with `job_not_offered`

#### Scenario: Vendor doesn't work on the make
- **WHEN** a booking is attempted at a vendor whose authorized makes exclude the truck's make
- **THEN** the booking is rejected with `job_not_offered`

#### Scenario: Vendor stopped towing
- **WHEN** a tow is required and the vendor's tow service is removed after a quote was offered
- **THEN** the booking is rejected with `quote_changed`
