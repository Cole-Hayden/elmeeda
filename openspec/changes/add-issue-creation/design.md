# Design

## Context

This is a new project with no existing code. See `proposal.md` for motivation and `specs/issue-management/spec.md` for the required behavior. The development machine already runs other Postgres containers on host ports 5432 and 5433, so this project must not use them.

## Goals / Non-Goals

**Goals:**

- Keep business logic independent of the web framework and the database, so both can change without touching it.
- Make every schema change a versioned, repeatable migration.
- Test the endpoint against real Postgres, not a substitute.

**Non-Goals:**

- Reading, updating, or deleting issues.
- Authentication and authorization.
- Containerizing the API or deploying to production. Only Postgres runs in Docker for now.

## Decisions

### Layered architecture with dependencies pointing inward

| Layer | Path | Responsibility |
| --- | --- | --- |
| Domain | `domain/` | The `Issue` entity. No framework imports. |
| Application | `application/` | The `IssueService` use case and the `IssueRepository` port. |
| Infrastructure | `infrastructure/` | SQLAlchemy models, engine, and the repository adapter. |
| API | `api/` | FastAPI routes, response schemas, and error mapping. |

`main.py` is the composition root that wires these together. A full hexagonal layout with separate packages per feature was rejected as too heavy for one entity. Putting everything in route handlers was rejected because it couples business logic to HTTP and SQL.

### FastAPI, async SQLAlchemy 2, and asyncpg

FastAPI provides validation and OpenAPI docs out of the box. Async I/O suits a database-bound API. Django was rejected because its ORM and admin bring more than this service needs.

### Alembic owns the schema

The app never calls `create_all`. A migration creates table `issues` with `issue_id UUID PRIMARY KEY`, so the primary key enforces uniqueness in the database.

### The domain generates a UUIDv4 identifier

Generating the ID in `Issue.create()` means an issue is complete before it reaches storage, and IDs cannot be enumerated. Database-generated IDs were rejected because they would make the domain depend on a save. The HTTP field is `issueId` and the column is `issue_id`; each layer follows its own naming convention.

### One transaction per repository write

The repository opens a short transaction for each write, which commits before the service returns. This guarantees that a 201 is only sent after the commit. A separate unit-of-work abstraction can be added when a use case spans multiple writes.

### Storage failures become a port-level error

The repository translates SQLAlchemy and connection errors into `StorageUnavailableError`, declared in the application layer. The API maps it to a generic 503 and logs the cause, so connection details never reach clients.

### Postgres 18 in Docker Compose, bound to loopback

The container publishes `127.0.0.1:5434` by default. Credentials come from an untracked `.env` file, and Compose refuses to start without them. Postgres 18 images store data below `/var/lib/postgresql`, so the named volume mounts there rather than at the older `.../data` path.

### Tests use a dedicated database

Integration tests create and migrate a separate `<database>_test` database, so running tests never touches development data.

## Risks / Trade-offs

- [The port-level error treats all SQLAlchemy errors as "unavailable", including programming errors] → The cause is logged with its stack trace, and there are no user-driven constraint failures yet.
- [The host port could become busy] → `POSTGRES_PORT` in `.env` changes it.
- [Random UUIDv4 keys index less efficiently than time-ordered keys at high volume] → This is acceptable now. The column type would not need to change to adopt UUIDv7 later.

## Migration Plan

1. Run `docker compose up -d --wait`.
2. Run `uv run alembic upgrade head`.

To roll back, run `uv run alembic downgrade base`. No data exists to migrate.
