"""Check every Must requirement from the working-session brief that can be checked without a
microphone.

Start the backend with the dev-only issue routes turned on, which the duplicate checks use to
stand in for a second call:

    ENABLE_DEV_API=true uv run uvicorn issue_tracker.main:create_app --factory --port 8001

Then run:

    uv run python scripts/check_requirements.py

It first runs every test suite and linter, then drives the Truck 214 scenario through the same
HTTP endpoints the browser uses, so the backend behaves exactly as it does during a call. Before the
live checks it reloads the mock data, which deletes every booking in the development database.
Run the checklist in scripts/voice_test_script.md afterwards for the parts that need a voice.

Options:
    --yes           Reload the mock data without asking first.
    --skip-suites   Skip the test suites and linters, and run only the live checks.
    --base-url URL  The backend's address. Defaults to http://127.0.0.1:8001.
"""

import argparse
import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
# Loaded by the mock data, with every detail except whether the truck can be driven.
SCENARIO_ISSUE_ID = "b0000000-0000-4000-8000-000000000214"

Json = dict[str, Any]


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes = 0

    def section(self, title: str) -> None:
        print(f"\n\033[1m{title}\033[0m")

    def check(self, label: str, ok: bool, detail: object = "") -> bool:
        if ok:
            self.passes += 1
            print(f"  \033[32mPASS\033[0m {label}")
        else:
            self.failures.append(label)
            print(f"  \033[31mFAIL\033[0m {label}")
            if detail != "":
                print(f"       got: {detail}")
        return ok


def run_suites(report: Report) -> None:
    report.section("Test suites and linters")
    commands = [
        ("Backend tests, including the gate and duplicate tests", ["uv", "run", "pytest", "-q"]),
        ("Ruff", ["uv", "run", "ruff", "check", "."]),
        ("Mypy", ["uv", "run", "mypy"]),
        ("Frontend relay tests", ["sh", "-c", "cd frontend && node --test src/*.test.js"]),
        ("Frontend lint", ["sh", "-c", "cd frontend && npm run lint --silent"]),
    ]
    for label, command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        tail = "\n".join((result.stdout + result.stderr).strip().splitlines()[-5:])
        report.check(label, result.returncode == 0, tail)


def reload_mock_data(assume_yes: bool) -> None:
    if not assume_yes:
        answer = input(
            "\nThe live checks reload the mock data, which deletes every booking in the development"
            " database. Continue? [y/N] "
        )
        if answer.strip().lower() not in ("y", "yes"):
            sys.exit("Stopped before changing anything.")
    subprocess.run(
        ["uv", "run", "python", "-m", "issue_tracker.infrastructure.seed"], cwd=ROOT, check=True
    )


class Backend:
    def __init__(self, client: httpx.AsyncClient, issue_id: str) -> None:
        self.client = client
        self.issue_id = issue_id

    async def tool(self, name: str, arguments: Json | None = None) -> Json:
        response = await self.client.post(
            f"/voice/calls/{self.issue_id}/tools/{name}", json=arguments or {}
        )
        response.raise_for_status()
        result: Json = response.json()
        return result

    async def timed_tool(self, name: str, arguments: Json | None = None) -> tuple[Json, float]:
        started = time.perf_counter()
        result = await self.tool(name, arguments)
        return result, time.perf_counter() - started

    async def read_back(self, confirmation_id: str, text: str) -> bool:
        response = await self.client.post(
            f"/voice/calls/{self.issue_id}/read-backs",
            json={"confirmationId": confirmation_id, "text": text},
        )
        response.raise_for_status()
        matched: bool = response.json()["matched"]
        return matched

    async def answer(self, confirmation_id: str, text: str) -> bool:
        response = await self.client.post(
            f"/voice/calls/{self.issue_id}/answers",
            json={"confirmationId": confirmation_id, "text": text},
        )
        response.raise_for_status()
        confirmed: bool = response.json()["confirmed"]
        return confirmed

    async def shops(self) -> dict[str, Json]:
        response = await self.client.get("/voice/shops")
        response.raise_for_status()
        return {shop["shopId"]: shop for shop in response.json()}

    async def set_fault(self, shop_id: str, fault: str) -> None:
        response = await self.client.put(f"/voice/shops/{shop_id}/fault", json={"fault": fault})
        response.raise_for_status()

    async def clear_faults(self) -> None:
        for shop_id in await self.shops():
            await self.set_fault(shop_id, "none")

    async def bays(self, shop_id: str) -> int:
        bays: int = (await self.shops())[shop_id]["openBays"]
        return bays

    async def prepare_and_confirm(self, shop_id: str) -> Json:
        prepared = await self.tool("prepare_booking", {"shopId": shop_id})
        await self.read_back(prepared["confirmationId"], prepared["readBack"])
        await self.answer(prepared["confirmationId"], "Yes, go ahead.")
        return prepared


def shop_ids(result: Json, key: str) -> dict[str, str]:
    """Each shop's ID in this part of a search result, mapped to its reason or name."""
    return {shop["shopId"]: shop.get("reason", shop["name"]) for shop in result.get(key, [])}


async def check_flow(report: Report, api: Backend) -> tuple[str, str]:
    report.section("Mock shops")
    shops = await api.shops()
    report.check("There are exactly 3 shops", len(shops) == 3, len(shops))
    report.check("All shops have open bays", all(s["openBays"] > 0 for s in shops.values()))

    report.section("Request and clarify")
    first = await api.tool("update_issue", {})
    report.check(
        "Only the missing detail is asked for (drivable)",
        first.get("missingDetails") == ["drivable"],
        first.get("missingDetails"),
    )
    clarified = await api.tool("update_issue", {"drivable": True})
    report.check(
        "Nothing is missing once drivable is given",
        clarified.get("missingDetails") == [],
        clarified.get("missingDetails"),
    )

    report.section("Search and options")
    search, seconds = await api.timed_tool("search_shops")
    options = search["options"]
    every_shop = shop_ids(search, "options") | shop_ids(search, "excluded")
    report.check("Search checks all 3 shops", set(every_shop) == set(shops), every_shop)
    report.check("At least two options to compare", len(options) >= 2, len(options))
    report.check(
        "Every option is within 30 miles and under $1,500",
        all(o["distanceMiles"] <= 30 and float(o["estimate"]) <= 1500 for o in options),
        options,
    )
    report.check(
        "Options include bays, estimate, distance and start time",
        all({"openBays", "estimate", "distanceMiles", "earliestStart"} <= set(o) for o in options),
    )
    report.check(f"Search answered in {seconds:.2f}s", seconds < 2)
    return options[0]["shopId"], options[1]["shopId"]


async def check_failure_switch(report: Report, api: Backend, shop_id: str) -> None:
    report.section("Failure switch and recovery")
    before = (await api.tool("search_shops"))["details"]

    await api.set_fault(shop_id, "timeout")
    timed_out, seconds = await api.timed_tool("search_shops")
    report.check(
        "Timeout: the shop is listed as unavailable with shop_timeout",
        shop_ids(timed_out, "unavailable").get(shop_id) == "shop_timeout",
        timed_out.get("unavailable"),
    )
    report.check(
        "Timeout: no price or bays are made up for it",
        shop_id not in shop_ids(timed_out, "options") | shop_ids(timed_out, "excluded"),
    )
    report.check(
        f"Timeout: the search really waits, then gives up ({seconds:.2f}s)", 1.5 < seconds < 5
    )
    report.check(
        "Timeout: the other shops are still offered",
        len(timed_out["options"]) >= 1,
        timed_out["options"],
    )

    await api.set_fault(shop_id, "error")
    errored = await api.tool("search_shops")
    report.check(
        "Error: the shop is listed as unavailable with shop_error",
        shop_ids(errored, "unavailable").get(shop_id) == "shop_error",
        errored.get("unavailable"),
    )

    await api.set_fault(shop_id, "no_open_bay")
    full = await api.tool("search_shops")
    report.check(
        "No open bay: the shop is excluded with no_open_bay",
        shop_ids(full, "excluded").get(shop_id) == "no_open_bay",
        full.get("excluded"),
    )
    prepared = await api.tool("prepare_booking", {"shopId": shop_id})
    report.check(
        "No open bay: the shop can't be prepared for booking",
        prepared.get("error") == "shop_not_available" and prepared.get("reason") == "no_open_bay",
        prepared,
    )

    for shop in await api.shops():
        await api.set_fault(shop, "timeout")
    silent = await api.tool("search_shops")
    report.check(
        "Every shop silent: status is shops_unavailable, not no_vendor",
        silent["status"] == "shops_unavailable" and silent["options"] == [],
        silent["status"],
    )

    await api.clear_faults()
    after = await api.tool("search_shops")
    report.check("The dispatcher's limits are unchanged", after["details"] == before)
    report.check(
        "Clearing the switch brings the shop back",
        shop_id in shop_ids(after, "options"),
        after["options"],
    )


async def check_gate(report: Report, api: Backend, shop_id: str, other_id: str) -> tuple[Json, str]:
    report.section("Confirmation gate (enforced by the backend)")
    bays_before = await api.bays(shop_id)

    result = await api.tool("book_repair", {"shopId": shop_id})
    report.check(
        "Booking before anything was prepared is refused",
        result.get("error") == "confirmation_required",
        result,
    )

    prepared = await api.tool("prepare_booking", {"shopId": shop_id})
    confirmation = prepared["confirmationId"]
    report.check("prepare_booking returns a readBack sentence", bool(prepared.get("readBack")))
    report.check(
        "Preparing doesn't take a bay", await api.bays(shop_id) == bays_before, bays_before
    )

    result = await api.tool("book_repair", {"shopId": shop_id})
    report.check(
        "Booking before the read-back is refused (read_back_required)",
        result.get("error") == "read_back_required",
        result,
    )

    early_yes = await api.answer(confirmation, "Yes")
    report.check("A yes before the read-back doesn't count", early_yes is False)
    result = await api.tool("book_repair", {"shopId": shop_id})
    report.check(
        "Booking after that early yes is still refused",
        result.get("error") == "read_back_required",
        result,
    )

    wrong = await api.read_back(confirmation, f"{prepared['shopName']}, about a grand, sometime")
    report.check("A read-back without the exact estimate and time doesn't count", wrong is False)

    matched = await api.read_back(confirmation, prepared["readBack"])
    report.check("The exact read-back counts", matched is True)
    result = await api.tool("book_repair", {"shopId": shop_id})
    report.check(
        "Booking after the read-back but before a yes is refused",
        result.get("error") == "confirmation_required",
        result,
    )

    for reply in ("No", "Yes, but wait", "Can you check the other shop?", "Hmm, let me think"):
        confirmed = await api.answer(confirmation, reply)
        result = await api.tool("book_repair", {"shopId": shop_id})
        report.check(
            f'"{reply}" isn\'t a yes, and nothing is booked',
            confirmed is False and result.get("error") == "confirmation_required",
            result,
        )

    confirmed = await api.answer(confirmation, "Yes, go ahead.")
    report.check("A clear yes is accepted", confirmed is True)
    result = await api.tool("book_repair", {"shopId": other_id})
    report.check(
        "That yes doesn't book a different shop",
        result.get("error") == "confirmation_required",
        result,
    )

    await api.set_fault(shop_id, "error")
    result = await api.tool("book_repair", {"shopId": shop_id})
    await api.set_fault(shop_id, "none")
    report.check(
        "A shop failing after the yes returns its real error, and books nothing",
        result.get("error") == "shop_error" and "bookingId" not in result,
        result,
    )
    result = await api.tool("book_repair", {"shopId": shop_id})
    report.check(
        "After a failure, the old yes no longer counts",
        result.get("error") == "confirmation_required",
        result,
    )
    report.check(
        "No bay was taken by any refused booking",
        await api.bays(shop_id) == bays_before,
        await api.bays(shop_id),
    )

    prepared = await api.prepare_and_confirm(shop_id)
    booking = await api.tool("book_repair", {"shopId": shop_id})
    report.check("After a new read-back and yes, the repair is booked", "bookingId" in booking)
    report.check(
        "The booking uses the estimate and time that were read back",
        booking.get("estimate") == prepared["estimate"]
        and booking.get("startTime") == prepared["startTime"],
        booking,
    )
    report.check(
        "The confirmation has the booking ID, shop, estimate and start time",
        {"bookingId", "shopName", "estimate", "startTime"} <= set(booking),
        booking,
    )
    report.check(
        "The booking took exactly one bay",
        await api.bays(shop_id) == bays_before - 1,
        await api.bays(shop_id),
    )
    return booking, prepared["confirmationId"]


async def check_duplicates(
    report: Report, api: Backend, booking: Json, confirmation_id: str, shop_id: str
) -> None:
    report.section("No duplicate bookings")
    booking_id = booking["bookingId"]
    bays = await api.bays(shop_id)

    retry = await api.tool("book_repair", {"shopId": shop_id})
    report.check(
        "Retrying returns the same booking, marked alreadyBooked",
        retry.get("bookingId") == booking_id and retry.get("alreadyBooked") is True,
        retry,
    )

    second_yes = await api.answer(confirmation_id, "Yes")
    retry = await api.tool("book_repair", {"shopId": shop_id})
    report.check(
        "A second yes returns the same booking",
        second_yes is False and retry.get("bookingId") == booking_id,
        retry,
    )

    parallel = await asyncio.gather(
        *(api.tool("book_repair", {"shopId": shop_id}) for _ in range(5))
    )
    report.check(
        "Five simultaneous retries all return the same booking",
        {result.get("bookingId") for result in parallel} == {booking_id},
        parallel,
    )

    prepared = await api.tool("prepare_booking", {"shopId": shop_id})
    report.check(
        "The booked issue can't be prepared again",
        prepared.get("reason") == "already_booked",
        prepared,
    )

    # A new call creates its own issue, so this stands in for the dispatcher calling back.
    created = await api.client.post(
        "/issues", json={"truckUnitNumber": "214", "problem": "coolant_leak"}
    )
    created.raise_for_status()
    new_call = Backend(api.client, created.json()["issueId"])
    found = await new_call.tool("search_shops")
    report.check(
        "A new call about the same truck finds the existing booking",
        found.get("existingBooking", {}).get("bookingId") == booking_id,
        found.get("existingBooking"),
    )
    report.check(
        "No retry took another bay", await api.bays(shop_id) == bays, await api.bays(shop_id)
    )

    report.section("The booking is stored")
    stored = (await api.client.get("/voice/bookings")).json()
    matching = [b for b in stored if b["bookingId"] == booking_id]
    report.check("The booking is listed by GET /voice/bookings", len(matching) == 1, stored)
    report.check("It's the only booking", len(stored) == 1, len(stored))


async def backend_problem(base_url: str) -> str | None:
    """Why the live checks can't run against this backend, checked before any data is reset."""
    async with httpx.AsyncClient(base_url=base_url, timeout=15) as client:
        try:
            await client.get("/voice/shops")
            # The dev routes answer an unknown ID with their own message, not FastAPI's default.
            probe = await client.get("/issues/00000000-0000-4000-8000-000000000000")
        except httpx.HTTPError:
            return f"No backend is running at {base_url}."
    if probe.json().get("detail") != "No issue has that ID.":
        return (
            "The dev-only issue routes are off. Restart the backend with ENABLE_DEV_API=true:\n"
            "    ENABLE_DEV_API=true uv run uvicorn issue_tracker.main:create_app --factory"
            " --port 8001"
        )
    return None


async def run_live_checks(report: Report, base_url: str) -> None:
    async with httpx.AsyncClient(base_url=base_url, timeout=15) as client:
        api = Backend(client, SCENARIO_ISSUE_ID)
        await api.clear_faults()
        try:
            shop_id, other_id = await check_flow(report, api)
            await check_failure_switch(report, api, shop_id)
            booking, confirmation_id = await check_gate(report, api, shop_id, other_id)
            if "bookingId" in booking:
                await check_duplicates(report, api, booking, confirmation_id, shop_id)
        finally:
            await api.clear_faults()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--skip-suites", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    args = parser.parse_args()

    # So these lines print in order with the output of the commands this runs.
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    report = Report()
    if not args.skip_suites:
        run_suites(report)
    problem = asyncio.run(backend_problem(args.base_url))
    if problem:
        report.section("Live checks")
        report.check("The backend is ready for the live checks", False, problem)
        sys.exit(1)
    reload_mock_data(args.yes)
    asyncio.run(run_live_checks(report, args.base_url))

    print(f"\n{report.passes} passed, {len(report.failures)} failed")
    if report.failures:
        sys.exit(1)
    print("Now run the voice checklist in scripts/voice_test_script.md.")


if __name__ == "__main__":
    main()
