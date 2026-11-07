# Spec Delta

## Purpose

Lets a dispatcher report a breakdown and book a repair by voice in the browser, with every price, vendor decision, and booking coming from the backend.

## ADDED Requirements

### Requirement: Start a voice call without exposing the API key
The system SHALL accept an SDP offer at `POST /voice/calls`, create an issue, connect the call to OpenAI using the server's API key, and return the `issueId` and SDP answer. The API key SHALL NOT be sent to the browser.

#### Scenario: Call starts
- **WHEN** a client posts a valid SDP offer
- **THEN** an issue is created and the response contains its `issueId` and the SDP answer

#### Scenario: Voice isn't configured
- **WHEN** no API key is configured
- **THEN** the response is `503` and no issue is created

#### Scenario: OpenAI rejects the call
- **WHEN** OpenAI returns an error or can't be reached
- **THEN** the response is `502` and the error doesn't include the API key

### Requirement: Ask only for missing details
The agent SHALL save details through a tool and SHALL ask only for what that tool reports as missing.

#### Scenario: Opening request leaves one detail unknown
- **WHEN** the dispatcher's request leaves only whether the truck can be driven unknown
- **THEN** the tool reports `drivable` as missing and the agent asks only about that

### Requirement: Resolve spoken places on the server
The system SHALL turn a spoken place into coordinates using known mock places, and the model SHALL NOT supply coordinates.

#### Scenario: Known place
- **WHEN** the dispatcher says "I-55 near Joliet"
- **THEN** the issue's location is saved with that place's stored coordinates

#### Scenario: Unknown place
- **WHEN** the place doesn't match a known place
- **THEN** the tool returns `location_unknown`, nothing is saved for location, and the agent asks again

### Requirement: Offer only eligible vendors
The search tool SHALL return only the triage result's options and exclusion reasons, with prices and times from the backend.

#### Scenario: Vendor is over budget
- **WHEN** a vendor is excluded with reason `over_budget`
- **THEN** it isn't returned as an option, and the reason is available for the agent to explain

### Requirement: Book only after the dispatcher confirms
The client SHALL send a booking only when `prepare_booking` succeeded for the same shop, estimate, and start time, and the dispatcher has spoken since that result was delivered. Any other booking call SHALL return `confirmation_required` and create nothing.

#### Scenario: Model books without preparing
- **WHEN** the model calls `book_repair` with no prepared booking
- **THEN** no request reaches the backend and the model receives `confirmation_required`

#### Scenario: Model books before the dispatcher replies
- **WHEN** the model calls `book_repair` before the dispatcher speaks again
- **THEN** no request reaches the backend and the model receives `confirmation_required`

#### Scenario: Details differ from what was prepared
- **WHEN** the shop, estimate, or start time differs from the prepared booking
- **THEN** no request reaches the backend and the model receives `confirmation_required`

#### Scenario: Dispatcher confirms
- **WHEN** the dispatcher speaks after the prepared booking and the model calls `book_repair` with the same details
- **THEN** the booking is sent to the backend

#### Scenario: Interrupted response
- **WHEN** a response containing a tool call is interrupted before it completes
- **THEN** the tool isn't run

### Requirement: Stay truthful when an action fails
Booking rejections and backend failures SHALL be returned to the model as tool results, and the agent SHALL NOT claim a booking that the backend didn't return.

#### Scenario: Shop loses its last bay
- **WHEN** a booking is rejected with `no_open_bay`
- **THEN** the agent receives that reason, says the booking failed, and searches again

#### Scenario: Backend unavailable
- **WHEN** a tool request fails or times out
- **THEN** the model receives a failure result, and the screen shows no booking

### Requirement: Confirm the booking by voice and on screen
The screen SHALL show the booking ID, shop, estimate, and start time from the booking tool's result, and the agent SHALL read back the same values.

#### Scenario: Booking succeeds
- **WHEN** the booking tool returns a booking
- **THEN** the screen shows its details, and the model receives the same details to read back

#### Scenario: Transcript mentions a booking
- **WHEN** the agent says a booking was made and no booking tool result exists
- **THEN** the screen shows no booking
