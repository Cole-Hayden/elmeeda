import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

DB_PATH = os.environ.get("ELMEEDA_DB", "elmeeda.db")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS issues (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            yield conn
    finally:
        conn.close()


class IssueCreate(BaseModel):
    id: UUID


class Issue(BaseModel):
    id: UUID
    status: str
    created_at: datetime


app = FastAPI(title="Elmeeda API")


@app.post("/api/issues", response_model=Issue, status_code=status.HTTP_201_CREATED)
def create_issue(payload: IssueCreate, response: Response) -> dict:
    """Create an issue from a client-generated GUID.

    Safe to retry: posting a GUID that already exists returns the existing
    issue with a 200 instead of creating a duplicate.
    """
    issue_id = str(payload.id)
    with connect() as conn:
        inserted = conn.execute(
            """
            INSERT INTO issues (id, status, created_at) VALUES (?, 'open', ?)
            ON CONFLICT (id) DO NOTHING
            """,
            (issue_id, datetime.now(UTC).isoformat()),
        ).rowcount
        row = conn.execute("SELECT * FROM issues WHERE id = ?", (issue_id,)).fetchone()

    if not inserted:
        response.status_code = status.HTTP_200_OK
    return dict(row)
