from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", str(tmp_path / "test.db"))
    return TestClient(main.app)


def test_creates_issue_from_guid(client):
    guid = str(uuid4())
    res = client.post("/api/issues", json={"id": guid})
    assert res.status_code == 201
    assert res.json()["id"] == guid
    assert res.json()["status"] == "open"


def test_repeat_post_returns_existing_issue(client):
    guid = str(uuid4())
    first = client.post("/api/issues", json={"id": guid})
    second = client.post("/api/issues", json={"id": guid})
    assert second.status_code == 200
    assert second.json() == first.json()


def test_rejects_invalid_guid(client):
    assert client.post("/api/issues", json={"id": "not-a-guid"}).status_code == 422
