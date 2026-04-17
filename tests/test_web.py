"""Tests for web API endpoints."""

import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from toybaru.trip_store import upsert_trips
from toybaru.web import app, _sessions


def _client():
    return TestClient(app)


def _authed_client():
    """Create a test client with a mock authenticated session."""
    mock_client = MagicMock()
    mock_client.auth = MagicMock()
    mock_client.auth.is_authenticated = True
    mock_client.api = MagicMock()
    mock_client.api._is_na = False

    token = "test-session-token"
    _sessions[token] = mock_client

    c = TestClient(app, cookies={"session": token})
    return c


def test_index_returns_html():
    resp = _client().get("/")
    assert resp.status_code == 200
    assert "Toybaru ReCare" in resp.text
    assert "text/html" in resp.headers["content-type"]


def test_languages_endpoint():
    resp = _client().get("/api/languages")
    assert resp.status_code == 200
    langs = resp.json()
    assert isinstance(langs, list)
    codes = [l["code"] for l in langs]
    assert "de" in codes
    assert "en" in codes
    for l in langs:
        assert "label" in l
        assert "locale" in l


def test_locale_de():
    resp = _client().get("/api/locale/de")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app"]["name"] == "Toybaru ReCare"
    assert data["_meta"]["locale"] == "de-DE"


def test_locale_en():
    resp = _client().get("/api/locale/en")
    assert resp.status_code == 200
    data = resp.json()
    assert data["_meta"]["locale"] == "en-GB"


def test_locale_fallback():
    resp = _client().get("/api/locale/xx")
    assert resp.status_code == 200
    data = resp.json()
    # Falls back to English
    assert data["_meta"]["locale"] == "en-GB"


def test_auth_status_unauthenticated():
    resp = _client().get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json()["authenticated"] == False


def test_db_count_empty():
    c = _authed_client()
    resp = c.get("/api/db/count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_db_trips_empty():
    c = _authed_client()
    resp = c.get("/api/db/trips")
    assert resp.status_code == 200
    assert resp.json() == []


def test_db_stats_empty():
    c = _authed_client()
    resp = c.get("/api/db/stats")
    assert resp.status_code == 200
    assert resp.json()["total_trips"] == 0


def test_db_count_with_data(sample_trips):
    upsert_trips(sample_trips)
    c = _authed_client()
    resp = c.get("/api/db/count")
    assert resp.json()["count"] == 5


def test_db_trip_detail(sample_trip):
    upsert_trips([sample_trip])
    c = _authed_client()
    resp = c.get(f"/api/db/trip/{sample_trip['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_trip["id"]
    assert "behaviours" in data
    assert "route" in data


def test_db_trip_not_found():
    c = _authed_client()
    resp = c.get("/api/db/trip/nonexistent-id")
    assert resp.status_code == 200
    assert "error" in resp.json()
