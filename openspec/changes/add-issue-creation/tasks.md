# Tasks

## 1. Project setup

- [x] 1.1 Create the `uv` project and dependencies, and verify `uv sync` succeeds
- [x] 1.2 Add typed settings loaded from `.env`, plus `.env.example` and `.gitignore`, and verify `.env` is ignored by git

## 2. Database

- [x] 2.1 Add a Compose file for Postgres 18 on `127.0.0.1:5434`, and verify the container reports healthy
- [x] 2.2 Add the SQLAlchemy `issues` model and Alembic setup with the first migration, and verify `alembic upgrade head` creates the table with a UUID primary key
- [x] 2.3 Verify the migration reverses cleanly with `alembic downgrade base` followed by `alembic upgrade head`

## 3. Issue creation

- [x] 3.1 Add the `Issue` entity, the `IssueRepository` port, and `IssueService`, and verify with unit tests using a fake repository
- [x] 3.2 Add the SQLAlchemy repository, translating storage errors, and verify through the integration tests in 3.4
- [x] 3.3 Add `POST /issues`, the response schema, the 503 handler, and the app factory
- [x] 3.4 Add integration tests against real Postgres for every scenario in the spec, and verify `pytest` passes
- [x] 3.5 Document setup and usage in `README.md`, and verify the documented commands run as written

## 4. End-to-end check

- [x] 4.1 Run the server, call `POST /issues` with `curl`, and verify the returned `issueId` exists in the database with `psql`
- [x] 4.2 Verify `ruff check`, `mypy`, and `openspec validate add-issue-creation --strict` pass

## Workflow follow-up

- Archive the change with `openspec archive add-issue-creation` after review.
