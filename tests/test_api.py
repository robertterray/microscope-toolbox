"""Tests for the FastAPI app."""

from unittest.mock import MagicMock

import requests
from fastapi.testclient import TestClient

import microscope_toolbox.api as api
from microscope_toolbox.api import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_get_item():
    r = client.get("/items/5")
    assert r.status_code == 200
    assert r.json() == {"id": 5, "name": "stub", "description": None}


def test_get_item_not_found():
    r = client.get("/items/0")
    assert r.status_code == 404


def test_create_item():
    r = client.post("/items", json={"name": "widget", "description": "a thing"})
    assert r.status_code == 201
    assert r.json() == {"id": 1, "name": "widget", "description": "a thing"}


def test_index_page():
    r = client.get("/")
    assert r.status_code == 200
    assert "Create Item" in r.text


def test_downdetector_up(monkeypatch):
    # Downdetector returns 403 to bots; that still counts as reachable
    monkeypatch.setattr(api.requests, "get", MagicMock(return_value=MagicMock(status_code=403)))
    r = client.get("/status/downdetector")
    assert r.status_code == 200
    assert r.json()["up"] is True
    assert r.json()["status_code"] == 403


def test_downdetector_server_error(monkeypatch):
    monkeypatch.setattr(api.requests, "get", MagicMock(return_value=MagicMock(status_code=503)))
    r = client.get("/status/downdetector")
    assert r.json()["up"] is False
    assert r.json()["status_code"] == 503


def test_downdetector_unreachable(monkeypatch):
    monkeypatch.setattr(api.requests, "get", MagicMock(side_effect=requests.ConnectTimeout()))
    r = client.get("/status/downdetector")
    assert r.json() == {
        "url": api.DOWNDETECTOR_URL,
        "up": False,
        "status_code": None,
        "latency_ms": None,
        "error": "ConnectTimeout",
    }


def test_bootstrap_served_locally():
    r = client.get("/vendor/bootstrap-5.3.3.min.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]
