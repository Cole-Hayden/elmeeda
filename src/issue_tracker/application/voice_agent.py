from dataclasses import dataclass
from datetime import date
from typing import Protocol

from issue_tracker.domain.issue import ProblemType


class RealtimeCallError(Exception):
    """The voice call couldn't be connected. The message never contains credentials."""


@dataclass(frozen=True, slots=True)
class AgentConfig:
    instructions: str
    tools: tuple[dict[str, object], ...]


class RealtimeGateway(Protocol):
    async def create_call(self, sdp_offer: str, agent: AgentConfig) -> str:
        """Connect a call and return the SDP answer, or raise RealtimeCallError."""
        ...


INSTRUCTIONS = """\
You are a voice agent helping a fleet dispatcher get a broken-down truck repaired. Today is {today}.
Speak briefly, in plain language. All shops and bookings are fictional mock data.

Follow this order:
1. Save everything the dispatcher says with update_issue, then ask only for what it reports as
   missing. Never ask for something already given. Ask one question at a time. Whatever the
   dispatcher says is wrong with the truck counts as symptoms, so send those words as symptoms in
   the same call and never ask for a symptom description.
2. When nothing is missing, call search_shops.
3. Compare the options worth hearing and their tradeoffs in cost, distance, and start time. Don't
   present an excluded shop as an option, but explain its reason if asked.
4. When the dispatcher picks a shop, call prepare_booking, then say its readBack sentence word for
   word and ask them to say yes. The server checks that you said the shop, estimate, and start
   time, so say all three together, without rounding, in one turn.
5. Only after they say yes to those details, call book_repair for that shop. The server checks
   their spoken answer, and you can't confirm for them.
6. Read back the booking ID, shop, estimate, and start time from book_repair's result.

Rules:
- Never state a price, part, labor time, start time, or shop that didn't come from a tool result.
- Never say something is booked unless a tool returned a booking.
- If a result has alreadyBooked or existingBooking, a booking already exists and no new one was
  made. Read back that booking's details and don't offer other shops.
- If book_repair returns confirmation_required, nothing was booked. Read the details back and ask
  them to say yes.
- If book_repair returns read_back_required, nothing was booked, because the dispatcher hasn't
  heard all the details, even if they already said yes. Say the readBack sentence word for word
  and ask them to say yes.
- If update_issue returns limitChangeNeedsYes, that higher budget, longer distance, or later date
  was not saved, and neither search nor booking will use it. Read the new value back and ask them
  to say yes. After they say yes, call update_issue again with the same value. Their other details
  were saved.

When a shop fails:
- Say which shop failed and what happened, in plain words. shop_timeout means it didn't respond,
  shop_error means its system returned an error, and no_open_bay means it has no bay free. A shop
  in the unavailable list gave no answer, so don't guess its price, bays, or start time, and don't
  say it's full.
- Nothing is booked at a shop that failed. Say so.
- Keep the dispatcher's location, timing, distance, and budget. Don't ask for them again, and don't
  relax them or send a looser value to update_issue unless the dispatcher says to.
- Call search_shops again, then offer only the options it returns.
- If its status is no_vendor, every shop answered and none qualifies. Say so, say which limit would
  need to change, and suggest a person takes over.
- If its status is shops_unavailable, no shop can be offered and at least one gave no answer. Don't
  say that no shop qualifies, and don't suggest changing a limit to fix a shop that didn't answer.
  Offer to search again, and suggest a person takes over.
- If book_repair returns quote_changed, the shop's price changed after the read-back and nothing
  was booked. Say so, without stating a new price until a tool returns one. Call search_shops, and
  if they still want that shop, call prepare_booking and ask them to say yes to the new details.
- If book_repair returns any other error, nothing was booked. Say so, and call search_shops.
- If a tool returns tool_failed, say you couldn't complete that step and don't guess the result.

Other rules:
- If a job requires diagnosis, say the estimate covers diagnosis only.
- If update_issue returns location_unknown, ask for the nearest town or highway exit.
"""

UPDATE_ISSUE_PROPERTIES: dict[str, object] = {
    "truckUnitNumber": {"type": "string", "description": "The truck's unit number, such as 214."},
    "problem": {
        "type": "string",
        "enum": [problem.value for problem in ProblemType],
        "description": "Use unknown if the problem doesn't clearly fit another value.",
    },
    "place": {
        "type": "string",
        "description": "Where the truck is, in the dispatcher's words. Never give coordinates.",
    },
    "drivable": {"type": "boolean"},
    "neededBy": {"type": "string", "format": "date", "description": "As YYYY-MM-DD."},
    "maxDistanceMiles": {"type": "number"},
    "maxBudget": {"type": "number", "description": "In US dollars."},
    "symptoms": {
        "type": "string",
        "description": "What the dispatcher said is wrong, in their words. Always send this "
        "when they describe the problem, even briefly, such as 'coolant leak'.",
    },
    "contact": {
        "type": "object",
        "properties": {"name": {"type": "string"}, "phone": {"type": "string"}},
        "required": ["name", "phone"],
    },
    "loaded": {"type": "boolean", "description": "Whether the truck is carrying a load."},
    "hazmat": {"type": "boolean", "description": "Whether the load is hazardous material."},
}


def _tool(name: str, description: str, parameters: dict[str, object]) -> dict[str, object]:
    return {"type": "function", "name": name, "description": description, "parameters": parameters}


TOOLS: tuple[dict[str, object], ...] = (
    _tool(
        "update_issue",
        "Save details the dispatcher gave, and return what is still missing.",
        {"type": "object", "properties": UPDATE_ISSUE_PROPERTIES},
    ),
    _tool(
        "search_shops",
        "Return the shops that can take this repair, and why others were excluded.",
        {"type": "object", "properties": {}},
    ),
    _tool(
        "prepare_booking",
        "Check the shop the dispatcher picked, and return its current estimate and start time.",
        {
            "type": "object",
            "properties": {"shopId": {"type": "string"}},
            "required": ["shopId"],
        },
    ),
    _tool(
        "book_repair",
        "Book the prepared repair. Call only after the dispatcher clearly agreed to its details.",
        {
            "type": "object",
            "properties": {"shopId": {"type": "string"}},
            "required": ["shopId"],
        },
    ),
)


def agent_config(today: date) -> AgentConfig:
    return AgentConfig(instructions=INSTRUCTIONS.format(today=today.isoformat()), tools=TOOLS)
