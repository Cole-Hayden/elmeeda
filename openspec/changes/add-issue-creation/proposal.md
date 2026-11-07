# Proposal

## Why

There is no backend yet. We need a Python service with its own Postgres database and a first working vertical slice, so later issue features have a foundation that is proven end to end.

## What Changes

- Add a Python backend service with a layered architecture.
- Add a project-owned Postgres database, run locally through Docker Compose.
- Add a versioned database migration that creates the issue table.
- Add `POST /issues`, which creates an issue and saves it to the database. An issue has only an `issueId` for now.

## Capabilities

### New Capabilities

- `issue-management`: Creating issues and storing them durably.

### Modified Capabilities

None.

## Impact

- **Code**: New service under `src/issue_tracker/`, migrations under `migrations/`, tests under `tests/`.
- **APIs**: New `POST /issues` endpoint.
- **Dependencies**: FastAPI, Uvicorn, SQLAlchemy, asyncpg, Alembic, pydantic-settings.
- **Systems**: A new Postgres 18 container, published on `127.0.0.1:5434`. Host ports 5432 and 5433 are already in use on the development machine.
