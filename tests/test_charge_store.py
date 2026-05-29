"""Tests for the charge-session store (NA charge history DB)."""

from toybaru.charge_store import (
    upsert_charges,
    get_charges_from_db,
    get_charge_count,
    get_latest_charge_timestamp,
)


def _session(start, **over):
    s = {
        "start_time": start,
        "end_time": "1700003600000",
        "soc_before_charging": "20%",
        "soc_after_charging": "80%",
        "total_charge_kwhr": "30.5",
        "charge_location_type": "DC",
        "address": "123 Main St",
        "latitude": 40.1,
        "longitude": -74.2,
        "watttime_details": {"co2_value": "1.2", "region": "NYISO"},
    }
    s.update(over)
    return s


def test_upsert_new_and_count():
    new, updated = upsert_charges([_session("1700000000000"), _session("1700100000000")], vin="VIN1")
    assert (new, updated) == (2, 0)
    assert get_charge_count() == 2


def test_upsert_dedup_on_vin_start():
    upsert_charges([_session("1700000000000", total_charge_kwhr="10")], vin="VIN1")
    # Same vin+start_time -> update, not a new row.
    new, updated = upsert_charges([_session("1700000000000", total_charge_kwhr="42")], vin="VIN1")
    assert (new, updated) == (0, 1)
    assert get_charge_count() == 1
    rows = get_charges_from_db(vin="VIN1")
    assert rows[0]["total_charge_kwhr"] == "42"  # value was updated


def test_same_start_different_vin_is_distinct():
    upsert_charges([_session("1700000000000")], vin="VIN1")
    new, _ = upsert_charges([_session("1700000000000")], vin="VIN2")
    assert new == 1
    assert get_charge_count() == 2


def test_get_charges_shape_and_order():
    upsert_charges([_session("1700000000000"), _session("1700200000000")], vin="VIN1")
    rows = get_charges_from_db(vin="VIN1")
    # newest first
    assert rows[0]["start_time"] == "1700200000000"
    # API-shaped keys + parsed watttime
    r = rows[0]
    assert r["soc_before_charging"] == "20%"
    assert r["charge_location_type"] == "DC"
    assert isinstance(r["watttime_details"], dict)
    assert r["watttime_details"]["region"] == "NYISO"


def test_session_without_start_time_skipped():
    new, updated = upsert_charges([{"soc_after_charging": "50%"}], vin="VIN1")
    assert (new, updated) == (0, 0)
    assert get_charge_count() == 0


def test_latest_timestamp():
    assert get_latest_charge_timestamp() is None
    upsert_charges([_session("1700000000000"), _session("1700300000000")], vin="VIN1")
    assert get_latest_charge_timestamp() == "1700300000000"
