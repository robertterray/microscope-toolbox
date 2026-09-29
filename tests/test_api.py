"""Tests for the FastAPI app."""

from unittest.mock import MagicMock

import pytest
import requests
from fastapi.testclient import TestClient

import microscope_toolbox.api as api
from microscope_toolbox.api import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_item() -> None:
    response = client.get("/items/5")
    assert response.status_code == 200
    assert response.json() == {"id": 5, "name": "stub", "description": None}


def test_get_item_not_found() -> None:
    response = client.get("/items/0")
    assert response.status_code == 404


def test_create_item() -> None:
    response = client.post("/items", json={"name": "widget", "description": "a thing"})
    assert response.status_code == 201
    assert response.json() == {"id": 1, "name": "widget", "description": "a thing"}


def test_index_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Create Item" in response.text


def test_downdetector_403_counts_as_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api.requests, "get", MagicMock(return_value=MagicMock(status_code=403))
    )
    response = client.get("/status/downdetector")
    assert response.status_code == 200
    assert response.json()["up"] is True
    assert response.json()["status_code"] == 403


def test_downdetector_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api.requests, "get", MagicMock(return_value=MagicMock(status_code=503))
    )
    response = client.get("/status/downdetector")
    assert response.json()["up"] is False
    assert response.json()["status_code"] == 503


def test_downdetector_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api.requests, "get", MagicMock(side_effect=requests.ConnectTimeout())
    )
    response = client.get("/status/downdetector")
    assert response.json() == {
        "url": api.DOWNDETECTOR_URL,
        "up": False,
        "status_code": None,
        "latency_ms": None,
        "error": "ConnectTimeout",
    }


def test_bootstrap_served_locally() -> None:
    response = client.get("/vendor/bootstrap-5.3.3.min.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
