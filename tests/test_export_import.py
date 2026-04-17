"""Tests for export/import roundtrip."""

import csv
import io
import json
import secrets
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from toybaru.trip_store import upsert_trips, get_trip_count, get_trips_from_db
from toybaru.web import app, _sessions, _csrf_tokens


@pytest.fixture
def client():
    """Create authenticated test client with CSRF token."""
    mock_client = MagicMock()
    mock_client.auth = MagicMock()
    mock_client.auth.is_authenticated = True
    mock_client.api = MagicMock()
    mock_client.api._is_na = False

    token = "test-export-session"
    csrf = secrets.token_hex(16)
    _sessions[token] = mock_client
    _csrf_tokens[token] = csrf

    c = TestClient(app, cookies={"session": token})
    yield c, csrf

    _sessions.pop(token, None)
    _csrf_tokens.pop(token, None)


def test_csv_export(client, sample_trips):
    c, csrf = client
    upsert_trips(sample_trips, vin="TEST")
    resp = c.get("/api/export/trips.csv?vin=TEST")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert len(rows) == 5
    assert "id" in rows[0]
    assert "start_ts" in rows[0]
    assert "avg_speed" in rows[0]
    # CSV should NOT include raw blobs
    assert "behaviours_json" not in rows[0]
    assert "route_json" not in rows[0]


def test_json_export(client, sample_trips):
    c, csrf = client
    upsert_trips(sample_trips, vin="TEST")
    resp = c.get("/api/export/trips.json?vin=TEST")
    assert resp.status_code == 200
    trips = json.loads(resp.text)
    assert len(trips) == 5
    # JSON should include behaviours and route
    assert "behaviours" in trips[0]
    assert "route" in trips[0]
    assert isinstance(trips[0]["behaviours"], list)
    assert isinstance(trips[0]["route"], list)
    # Should NOT include raw_json
    assert "raw_json" not in trips[0]


def test_json_reimport_roundtrip(client, sample_trips):
    c, csrf = client
    upsert_trips(sample_trips, vin="TEST")
    # Export
    resp = c.get("/api/export/trips.json?vin=TEST")
    exported = json.loads(resp.text)
    assert len(exported) == 5

    # Re-import the exported data
    resp = c.post("/api/reimport", json={"trips": exported}, headers={"X-CSRF-Token": csrf})
    assert resp.status_code == 200
    result = resp.json()
    assert result["updated"] == 5  # All already exist
    assert result["total"] == 5

    # Verify data integrity
    db_trips = get_trips_from_db(limit=10, vin="TEST")
    assert len(db_trips) == 5
    for trip in db_trips:
        assert trip["avg_speed"] is not None
        assert trip["score_global"] is not None


def test_reimport_upsert(client, sample_trip):
    c, csrf = client
    upsert_trips([sample_trip], vin="TEST")
    assert get_trip_count() == 1

    # Export
    resp = c.get("/api/export/trips.json?vin=TEST")
    exported = json.loads(resp.text)

    # Re-import same data - should update, not duplicate
    resp = c.post("/api/reimport", json={"trips": exported}, headers={"X-CSRF-Token": csrf})
    result = resp.json()
    assert result["updated"] == 1
    assert result["new"] == 0
    assert get_trip_count() == 1
