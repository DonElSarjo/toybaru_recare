"""Tests for trip_store and trip_stats modules."""

from toybaru.trip_store import (
    upsert_trips, get_trip_count, get_trips_from_db, get_latest_trip_timestamp,
)
from toybaru.trip_stats import get_detailed_stats, estimate_kwh_100km


def test_upsert_new(sample_trip):
    new, updated = upsert_trips([sample_trip])
    assert new == 1
    assert updated == 0
    assert get_trip_count() == 1


def test_upsert_duplicate(sample_trip):
    upsert_trips([sample_trip])
    new, updated = upsert_trips([sample_trip])
    assert new == 0
    assert updated == 1
    assert get_trip_count() == 1


def test_upsert_with_vin(sample_trip):
    upsert_trips([sample_trip], vin="JF1TEST123")
    trips = get_trips_from_db(limit=1)
    assert trips[0]["vin"] == "JF1TEST123"


def test_get_trips_from_db(sample_trips):
    upsert_trips(sample_trips)
    trips = get_trips_from_db(limit=10)
    assert len(trips) == 5
    # Should be DESC order (newest first)
    assert trips[0]["start_ts"] > trips[-1]["start_ts"]


def test_get_trips_date_filter(sample_trips):
    upsert_trips(sample_trips)
    trips = get_trips_from_db(from_date="2025-08-01", to_date="2025-09-30")
    assert len(trips) == 2  # highway + night


def test_get_trips_vin_filter(sample_trip):
    upsert_trips([sample_trip], vin="VIN-A")
    from tests.conftest import _make_trip
    trip_b = _make_trip("trip-b", "2025-07-01T10:00:00Z")
    upsert_trips([trip_b], vin="VIN-B")
    assert get_trip_count() == 2
    assert len(get_trips_from_db(vin="VIN-A")) == 1
    assert len(get_trips_from_db(vin="VIN-B")) == 1


def test_get_latest_timestamp(sample_trips):
    upsert_trips(sample_trips)
    latest = get_latest_trip_timestamp()
    assert latest == "2026-03-10T12:00:00Z"


def test_get_trip_count_empty():
    assert get_trip_count() == 0


def test_get_detailed_stats(sample_trips):
    upsert_trips(sample_trips)
    stats = get_detailed_stats()
    assert stats["total_trips"] == 5
    assert stats["total_km"] > 0
    assert stats["total_hours"] > 0
    assert stats["avg_speed"] > 0
    assert stats["max_speed"] == 140
    assert stats["avg_score"] > 0
    assert stats["first_trip"] is not None
    assert stats["last_trip"] is not None
    assert stats["reku_pct"] > 0
    assert stats["eco_pct"] > 0
    assert stats["power_pct"] > 0
    assert len(stats["monthly"]) > 0
    assert len(stats["weekday"]) > 0
    assert len(stats["records"]) > 0
    assert "longest_trip" in stats["records"]


def test_get_detailed_stats_date_filter(sample_trips):
    upsert_trips(sample_trips)
    stats = get_detailed_stats(from_date="2025-08-01", to_date="2025-09-30")
    assert stats["total_trips"] == 2


def test_estimate_kwh_city():
    result = estimate_kwh_100km(avg_speed=30, reku_pct=30, power_pct=5)
    assert 12 <= result <= 20


def test_estimate_kwh_mixed():
    result = estimate_kwh_100km(avg_speed=55, reku_pct=25, power_pct=20)
    assert 14 <= result <= 22


def test_estimate_kwh_highway():
    result = estimate_kwh_100km(avg_speed=120, reku_pct=5, power_pct=40)
    assert 25 <= result <= 40


def test_trips_have_est_kwh(sample_trips):
    upsert_trips(sample_trips)
    trips = get_trips_from_db()
    for trip in trips:
        assert "est_kwh_100km" in trip
        assert trip["est_kwh_100km"] is not None
        assert 5 <= trip["est_kwh_100km"] <= 50
