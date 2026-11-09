# Voice test script

`scripts/check_requirements.py` checks everything the backend decides. This script covers what only a real call can show: speech in and out, the agent's wording, interruptions, and the screen. It takes about 15 minutes.

## Before you start

1. Make sure `OPENAI_API_KEY` is set in `.env`.
2. Start Postgres, the backend, and the frontend, as described in the README.
3. Load fresh mock data. This deletes every booking:

   ```bash
   uv run python -m issue_tracker.infrastructure.seed
   ```

4. Open http://localhost:5173 in Chrome, not in the Claude app's built-in browser, which blocks microphones.
5. Open **Demo controls** and check that all three shops say **Working normally**.

Each run books Truck 214, so reload the mock data before every run. Faults stay set until you change them or restart the backend.

## Run 1: The happy path

Covers voice in and out, the full flow, the confirmation gate, the tool-call log, and the final confirmation.

| # | You say | Check |
|---|---|---|
| 1 | Select **Start call** and allow the microphone. | The status says **Listening**. |
| 2 | "Truck 214 is down on I-55 near Joliet with a coolant leak. I need a shop that can take it today, within 30 miles, under $1,500. What can you set up?" | You hear the agent reply. It asks only whether the truck can be driven, and doesn't ask again for the location, timing, or budget. The log shows `update_issue`. |
| 3 | "Yes, it can be driven." | The agent calls `search_shops`. The **Shops** list shows two options, and Millrace Diesel is crossed out as over budget. |
| 4 | Listen. | The agent compares the two options on cost, distance, and start time, and doesn't offer Millrace. Every price and time it says matches the screen. |
| 5 | "Let's go with Woodridge." | `prepare_booking` appears in the log. The screen says **Waiting for your yes. Nothing is booked yet.** The agent reads back the shop, estimate, and start time, and asks for a yes. |
| 6 | Wait for it to finish, then say "Yes, go ahead." | The log shows `read_back_check`, then `confirmation_answer`, then `book_repair` with **ok**. |
| 7 | Listen. | The agent reads back the booking ID, shop, estimate, and start time, and the **Booked** panel shows the same four values. The bookings list shows the new booking. **Demo controls** shows Woodridge with one fewer open bay. |
| 8 | Open a few log entries. | Each one shows its arguments, its result or error, and a duration in ms. |

## Run 2: Saying no, and talking over the read-back

Covers the confirmation gate. Reload the mock data first.

| # | You say | Check |
|---|---|---|
| 1 | Repeat steps 1 to 5 of Run 1. | The agent reads back the details. |
| 2 | While it's still reading back, say "Yes." | Nothing is booked. If the agent calls `book_repair`, it returns `read_back_required` or `confirmation_required`, and the agent reads the details back again. |
| 3 | When it finishes, say "No, wait." | Nothing is booked. The agent doesn't claim it booked anything. |
| 4 | "Actually, use Rockdale instead." | A new `prepare_booking` for Rockdale, and a new read-back with Rockdale's details. |
| 5 | Say "Yes" after it finishes. | Rockdale is booked, not Woodridge. |

## Run 3: No duplicates

Continue straight on from Run 1 or Run 2, with the booking still in place.

| # | You say | Check |
|---|---|---|
| 1 | "Yes, book it." | Any `book_repair` returns the same booking ID with `alreadyBooked`. The screen says **Already booked. No new booking was made.** |
| 2 | "Yes. Yes, go ahead." | Still the same booking ID. The open bays in **Demo controls** don't change. |
| 3 | Select **End call**, then **Start call**, and say "Truck 214 is down near Joliet with a coolant leak, it's drivable, today, 30 miles, under $1,500." | The agent finds the existing booking, reads it back, and doesn't offer other shops. The bookings list still has one booking. |
| 4 | Restart the backend and reload the page. | The booking is still listed, and the shop still has one fewer bay. |

## Run 4: A shop fails

Covers the failure switch and recovery. Reload the mock data first, and run this once for each fault: **Time out**, **Return an error**, and **No open bay**.

| # | You do | Check |
|---|---|---|
| 1 | Repeat steps 1 to 4 of Run 1. | The agent compares the two options. |
| 2 | In **Demo controls**, set Woodridge to the fault you're testing. | The section title shows **(1 failing)**. |
| 3 | Say "Let's go with Woodridge." | `prepare_booking` returns `shop_not_available` with the reason `shop_timeout` (after about 2 seconds), `shop_error`, or `no_open_bay`. Nothing is read back or booked. |
| 4 | For the variant: repeat with a fresh load, but flip the switch after you've said "Yes" to Woodridge's read-back and before the agent books. This is hard to time by voice, and `check_requirements.py` already covers it. | `book_repair` returns the real error, and nothing is booked. |
| 5 | Listen. | The agent names Woodridge and says what really happened: it didn't respond, its system returned an error, or it has no bay free. It says nothing was booked. It doesn't make up a price or time for Woodridge, and doesn't say a shop that timed out is full. |
| 6 | Listen. | The agent calls `search_shops` again without asking for the location, timing, distance, or budget again, and offers Rockdale. |
| 7 | "Okay, book Rockdale." Then, after the read-back, "Yes." | Rockdale is booked within the original limits. |

## Run 5: Every shop fails

Reload the mock data first.

| # | You do | Check |
|---|---|---|
| 1 | Set all three shops to **Time out**. | |
| 2 | Repeat steps 1 to 3 of Run 1. | `search_shops` returns `shops_unavailable`. The agent says the shops didn't respond, doesn't say that no shop qualifies, doesn't suggest raising the budget or distance, and offers to search again or hand over to a person. |
| 3 | Set every shop back to **Working normally**, and say "Try again." | The options come back. |

## Run 6: Raising a limit needs a yes

Reload the mock data first.

| # | You say | Check |
|---|---|---|
| 1 | Repeat steps 1 to 3 of Run 1. | |
| 2 | "Actually, the budget can go to $2,000." | The `update_issue` result has `limitChangeNeedsYes`. The agent reads the new budget back and asks for a yes. |
| 3 | "Yes." | The agent calls `update_issue` again, and the next search can include Millrace. |
