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

### Requirement: List booked repairs on screen
The system SHALL expose `GET /voice/bookings`, which returns every booking with its truck, problem, location, shop, estimate, and start time. The screen SHALL list these instead of issues, and SHALL reload the list when a call returns a booking.

#### Scenario: Issue without a booking
- **WHEN** an issue has no booking
- **THEN** it isn't listed

#### Scenario: Booking made during a call
- **WHEN** a tool returns a booking
- **THEN** the list reloads and shows it without reloading the page

### Requirement: A yes counts only after the details were said
The backend SHALL ignore a yes to a prepared booking until the agent has finished saying that shop, estimate, and start time. The browser SHALL report what the agent said only after its audio has finished playing, and the model SHALL have no tool that records this.

#### Scenario: Model books before reading back
- **WHEN** the model calls `book_repair` before it has said the prepared details
- **THEN** the backend returns `read_back_required` and nothing is booked

#### Scenario: Read-back leaves out or misstates a detail
- **WHEN** the agent asks for a yes without saying the prepared shop, estimate, or start time, or says a different one instead
- **THEN** that isn't a read-back, a yes to it doesn't count, and the backend returns `read_back_required`

#### Scenario: Yes said before the details were spoken
- **WHEN** a yes reaches the backend before the read-back, and the read-back follows
- **THEN** the yes doesn't carry over, and the backend returns `confirmation_required`

#### Scenario: Dispatcher talks over the read-back
- **WHEN** the dispatcher speaks before the read-back has finished playing
- **THEN** that speech doesn't count as a reply, and the read-back doesn't count unless it's said again in full

### Requirement: Book only after the dispatcher confirms
The backend SHALL create a booking only when `prepare_booking` succeeded for the same shop and the dispatcher's reply to that read-back was a clear yes, booking the estimate and start time `prepare_booking` stored. Any other booking call SHALL return `confirmation_required`, or `read_back_required` if the details haven't been said, and create nothing. The model SHALL have no tool that records a reply.

#### Scenario: Model books without preparing
- **WHEN** the model calls `book_repair` with no prepared booking
- **THEN** the backend returns `confirmation_required` and nothing is booked

#### Scenario: Model books before the dispatcher replies
- **WHEN** the model calls `book_repair` after the read-back and before the dispatcher replies
- **THEN** the backend returns `confirmation_required` and nothing is booked

#### Scenario: Reply is only counted after the read-back
- **WHEN** the dispatcher speaks after the read-back finished playing
- **THEN** that speech counts as a reply, and the latest reply decides

#### Scenario: Dispatcher says anything but a clear yes
- **WHEN** the dispatcher replies "no, hold on", asks a question, or gives an unclear or mixed answer
- **THEN** the backend returns `confirmation_required` to `book_repair` and nothing is booked

#### Scenario: Dispatcher takes back a yes
- **WHEN** the dispatcher says yes and then says "actually, wait"
- **THEN** nothing is booked until they say yes again

#### Scenario: Yes said before the read-back
- **WHEN** speech that started before the read-back finished is transcribed after it
- **THEN** that speech doesn't count as a reply

#### Scenario: Shop differs from what was prepared
- **WHEN** the model calls `book_repair` for a shop other than the prepared one
- **THEN** the backend returns `confirmation_required` and nothing is booked

#### Scenario: Another shop is prepared
- **WHEN** a second shop is prepared after a yes to the first, including a late transcript of that yes
- **THEN** the yes doesn't apply to the second shop

#### Scenario: Model sends its own price
- **WHEN** the model sends an estimate or start time with `book_repair`
- **THEN** they're ignored and the prepared values are booked

#### Scenario: Dispatcher confirms
- **WHEN** the dispatcher says yes to the read-back and the model calls `book_repair` for the same shop
- **THEN** the booking is created

#### Scenario: Interrupted response
- **WHEN** a response containing a tool call is interrupted before it completes
- **THEN** the tool isn't run

### Requirement: Never create a duplicate booking
A truck SHALL have at most one booking, whatever the needed-by date, across retries, repeated confirmations, and separate calls. Any repeat SHALL return the existing booking, marked `alreadyBooked`, and SHALL NOT take another bay.

#### Scenario: Dispatcher says yes twice
- **WHEN** `book_repair` is called again after a booking was created
- **THEN** the same booking is returned with `alreadyBooked`, and open bays don't change

#### Scenario: Booking response is lost
- **WHEN** the browser gets no answer to `book_repair`
- **THEN** it asks once more and receives the booking if one was committed

#### Scenario: New call for a booked truck
- **WHEN** a new call searches for the same truck, with the same or a different needed-by date
- **THEN** the search returns the status `booked` with `existingBooking` and no options

#### Scenario: Two calls race for one truck
- **WHEN** two calls try to book the same truck at the same time
- **THEN** one booking is created

### Requirement: Fail one shop on demand
The system SHALL provide a control, usable during a call, that makes one shop time out, return an error, or have no open bay. It SHALL affect the agent's tools only, and SHALL NOT change stored shop data or REST issue responses.

#### Scenario: Shop times out during search
- **WHEN** a shop is set to time out and the agent searches
- **THEN** the search waits for the deadline, reports the shop in `unavailable` with `shop_timeout`, and still returns the other shops' results

#### Scenario: Shop returns an error during search
- **WHEN** a shop is set to return an error and the agent searches
- **THEN** the shop is in `unavailable` with `shop_error`, and the other shops' results are returned

#### Scenario: Shop has no open bay
- **WHEN** a shop is set to have no open bay and the agent searches
- **THEN** the shop is excluded with `no_open_bay`

#### Scenario: Switch flipped after the yes
- **WHEN** a shop is set to fail after the dispatcher confirmed it
- **THEN** `book_repair` returns that failure, nothing is booked, and booking again needs a new read-back and yes

### Requirement: Log every tool call
The screen SHALL show each tool call and each recorded reply, with its arguments, its result or error, and how long it took.

#### Scenario: Tool call fails
- **WHEN** a tool returns an error
- **THEN** the log shows the error, its arguments, and its duration

#### Scenario: Model sends invalid arguments
- **WHEN** a tool call's arguments can't be parsed
- **THEN** the log shows the raw arguments and the error, and nothing reaches the backend

### Requirement: Stay truthful when an action fails
Booking rejections and backend failures SHALL be returned to the model as tool results, and the agent SHALL NOT claim a booking that the backend didn't return.

#### Scenario: Shop loses its last bay
- **WHEN** a booking is rejected with `no_open_bay`
- **THEN** the agent receives that reason, says the booking failed, and searches again

#### Scenario: Shop fails
- **WHEN** a tool reports that a shop timed out or returned an error
- **THEN** the agent says what happened, invents nothing about that shop, keeps the dispatcher's limits, and offers only what a new search returns

#### Scenario: Nothing to offer because a shop gave no answer
- **WHEN** a search has no options and at least one shop is in `unavailable`
- **THEN** the status is `shops_unavailable`, not `no_vendor`, and the agent doesn't say that no shop qualifies

#### Scenario: Price changes after the read-back
- **WHEN** a booking is rejected with `quote_changed`
- **THEN** the agent says nothing was booked, searches again, and states a new price only from a tool result

#### Scenario: Backend unavailable
- **WHEN** a tool request fails or times out
- **THEN** the model receives a failure result, and the screen shows no booking

### Requirement: Loosen a limit only after the dispatcher confirms
When `update_issue` would raise a budget or distance limit, or move a needed-by date later, on an issue that already has that limit, the backend SHALL NOT save that value until the dispatcher's reply to its read-back is a clear yes. Other details in the same call SHALL still be saved.

#### Scenario: Model loosens a limit
- **WHEN** the model calls `update_issue` with a higher budget and the dispatcher hasn't confirmed it
- **THEN** the result has `limitChangeNeedsYes`, the old budget stays saved, and searches keep using it

#### Scenario: Dispatcher confirms the new limit
- **WHEN** the dispatcher says yes to the read-back and the model repeats the same change
- **THEN** the new limit is saved

#### Scenario: Yes to a different value
- **WHEN** the model sends a different value after the dispatcher said yes
- **THEN** that value isn't saved and needs its own read-back and yes

#### Scenario: Limit is set or tightened
- **WHEN** a limit is set for the first time or made stricter
- **THEN** it is saved without a read-back

### Requirement: Confirm the booking by voice and on screen
The screen SHALL show the booking ID, shop, estimate, and start time from the booking tool's result, and the agent SHALL read back the same values.

#### Scenario: Booking succeeds
- **WHEN** the booking tool returns a booking
- **THEN** the screen shows its details, and the model receives the same details to read back

#### Scenario: Transcript mentions a booking
- **WHEN** the agent says a booking was made and no booking tool result exists
- **THEN** the screen shows no booking
