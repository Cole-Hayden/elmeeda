# Tasks

## 1. Routes

- [x] 1.1 Remove `PATCH /issues/{issueId}` and `GET /issues`, and the issue list code only they used
- [x] 1.2 Mount `POST /issues` and `GET /issues/{issueId}` only when `ENABLE_DEV_API` is on, hidden from the API docs, and verify both states with an integration test
- [x] 1.3 Move the models, dependencies, and errors the voice routes share into `api/schemas.py` and `api/dependencies.py`

## 2. Tests and docs

- [x] 2.1 Move the update tests that cover behaviour the voice path needs onto the `update_issue` tool, and add a test that `PATCH` and the list are gone
- [x] 2.2 Make `scripts/check_requirements.py` check the dev routes are on before it reloads any data
- [x] 2.3 Update `README.md`, and verify `pytest`, `ruff check`, `mypy`, and `openspec validate make-issue-routes-dev-only --strict` pass
