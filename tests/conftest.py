"""Shared test fixtures."""

import json
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path):
    """Redirect DATA_DIR to temp directory for test isolation."""
    with patch("toybaru.database.DATA_DIR", tmp_path), \
         patch("toybaru.const.DATA_DIR", tmp_path):
        yield tmp_path


def _make_trip(trip_id, start_ts, length_m=5000, duration_s=600, avg_speed=30.0,
               max_speed=60.0, eco_dist=3000, charge_dist=1200, power_dist=800,
               score=75, night=False, highway_m=0, vin=None):
    ev_dist = eco_dist + charge_dist + power_dist
    return {
        "id": trip_id,
        "category": 0,
        "summary": {
            "startTs": start_ts,
            "endTs": start_ts.replace("10:", "10:1"),
            "length": length_m,
            "duration": duration_s,
            "durationIdle": 30,
            "maxSpeed": max_speed,
            "averageSpeed": avg_speed,
            "fuelConsumption": 0.0,
            "startLat": 54.15, "startLon": 10.43,
            "endLat": 54.16, "endLon": 10.44,
            "nightTrip": night,
            "lengthOverspeed": 100,
            "durationOverspeed": 10,
            "lengthHighway": highway_m,
            "durationHighway": highway_m // 30 if highway_m else 0,
            "countries": ["DE"],
        },
        "scores": {
            "global": score,
            "acceleration": score - 5,
            "braking": score + 5,
            "constantSpeed": score - 2,
            "advice": 1,
        },
        "hdc": {
            "evTime": duration_s,
            "evDistance": ev_dist,
            "chargeTime": int(duration_s * 0.3),
            "chargeDist": charge_dist,
            "ecoTime": int(duration_s * 0.5),
            "ecoDist": eco_dist,
            "powerTime": int(duration_s * 0.2),
            "powerDist": power_dist,
        },
        "behaviours": [
            {"lat": 54.155, "lon": 10.435, "ts": start_ts, "type": "B", "good": False,
             "diagnosticMsg": 5, "coachingMsg": 5, "context": {"slope": 0.0},
             "priority": True, "severity": 10000.0},
        ],
        "route": [
            {"lat": 54.15, "lon": 10.43, "overspeed": False, "highway": False,
             "indexInPoints": 0, "mode": 1, "isEv": True},
            {"lat": 54.16, "lon": 10.44, "overspeed": False, "highway": False,
             "indexInPoints": 1, "mode": 0, "isEv": True},
        ],
    }


@pytest.fixture
def sample_trip():
    return _make_trip("trip-001", "2025-06-15T10:00:00Z")


@pytest.fixture
def sample_trips():
    return [
        _make_trip("trip-city", "2025-06-10T08:00:00Z", length_m=3000, avg_speed=25, max_speed=50, score=65),
        _make_trip("trip-rural", "2025-07-15T14:00:00Z", length_m=45000, avg_speed=55, max_speed=100, score=82),
        _make_trip("trip-highway", "2025-08-20T06:00:00Z", length_m=180000, avg_speed=100, max_speed=140, score=92, highway_m=150000),
        _make_trip("trip-night", "2025-09-01T23:30:00Z", length_m=8000, avg_speed=35, max_speed=70, score=70, night=True),
        _make_trip("trip-recent", "2026-03-10T12:00:00Z", length_m=12000, avg_speed=40, max_speed=80, score=78),
    ]
