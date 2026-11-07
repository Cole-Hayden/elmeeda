# Issue Tracker

A Python backend for creating issues, backed by Postgres. Requires [uv](https://docs.astral.sh/uv/) and Docker.

## Run it

```bash
cp .env.example .env
```

```bash
docker compose up -d --wait
```

```bash
uv run alembic upgrade head
```

```bash
uv run uvicorn issue_tracker.main:create_app --factory --port 8001
```

Interactive API docs are at http://127.0.0.1:8001/docs.

## Run the frontend

The dev server sends `/api` requests to the backend on port 8001. Opening the page creates an issue.

```bash
cd frontend && npm install && npm run dev
```

## Load the mock data

This loads the fictional trucks, repair shops, and Truck 214 scenario. Run it again to reset between demos. It deletes all bookings, trucks, shops, and any issue attached to a truck.

```bash
uv run python -m issue_tracker.infrastructure.seed
```

To demo a shop failing, take away its open bays after the agent has offered it:

```bash
docker compose exec db psql -U issue_tracker -d issue_tracker -c "UPDATE maintenance_shops SET open_bays = 0 WHERE name LIKE 'Rockdale%';"
```

## Create an issue

Send whatever is known about the breakdown. Every field is optional, so a request with no body also creates an issue. `truckUnitNumber` must match an existing truck, so load the mock data first.

```bash
curl -i -X POST http://127.0.0.1:8001/issues -H 'Content-Type: application/json' -d '{"truckUnitNumber": "214", "problem": "coolant_leak", "location": {"description": "I-55 near Joliet, IL", "latitude": 41.49, "longitude": -88.195}, "drivable": false, "neededBy": "2026-11-07", "maxDistanceMiles": 30, "maxBudget": "1500.00"}'
```

The response has status `201` and a server-generated ID:

```json
{"issueId": "3f2b8c1e-6a4d-4e7b-9c10-2d5f8a7b1e34"}
```

`problem` is one of `coolant_leak`, `tire_blowout`, or `brake_failure`. An unknown truck or an invalid value returns `422`, and nothing is saved. If the database is unavailable, the response has status `503`.

## Check the database

Postgres listens on `127.0.0.1:5434`.

```bash
docker compose exec db psql -U issue_tracker -d issue_tracker -c 'SELECT * FROM issues;'
```

## Test

Postgres must be running. Integration tests recreate a separate `issue_tracker_test` database each run, so your development data isn't touched.

```bash
uv run pytest
```

```bash
uv run ruff check . && uv run mypy
```

## Architecture

Dependencies point inward, so the domain knows nothing about HTTP or SQL.

| Path | Responsibility |
| --- | --- |
| `src/issue_tracker/api/` | HTTP routes and response schemas |
| `src/issue_tracker/application/` | Use cases and the repository interface |
| `src/issue_tracker/domain/` | The `Issue`, `Truck`, `MaintenanceShop`, and `Booking` entities |
| `src/issue_tracker/infrastructure/` | SQLAlchemy models, repository implementations, and fictional mock data |
| `src/issue_tracker/main.py` | App factory that wires the layers together |
| `frontend/` | React UI |
| `migrations/` | Alembic schema migrations |
| `openspec/` | Specs and change proposals |
