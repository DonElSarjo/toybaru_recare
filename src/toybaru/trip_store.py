"""Trip storage - CRUD operations for the trips database."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from toybaru.database import get_db as _get_db_raw, load_queries
from toybaru.trip_stats import estimate_kwh_100km

_UPSERT_SQL = """
    INSERT INTO trips (
        id, vin, category, start_ts, end_ts, length_m, duration_s, duration_idle_s,
        max_speed, avg_speed, fuel_consumption,
        start_lat, start_lon, end_lat, end_lon, night_trip,
        length_overspeed, duration_overspeed, length_highway, duration_highway,
        countries,
        score_global, score_acceleration, score_braking, score_constant_speed, score_advice,
        hdc_ev_time, hdc_ev_distance, hdc_charge_time, hdc_charge_dist,
        hdc_eco_time, hdc_eco_dist, hdc_power_time, hdc_power_dist,
        behaviours_json, route_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        vin=excluded.vin,
        length_m=excluded.length_m, duration_s=excluded.duration_s,
        max_speed=excluded.max_speed, avg_speed=excluded.avg_speed,
        score_global=excluded.score_global, score_acceleration=excluded.score_acceleration,
        score_braking=excluded.score_braking, score_constant_speed=excluded.score_constant_speed,
        hdc_ev_time=excluded.hdc_ev_time, hdc_ev_distance=excluded.hdc_ev_distance,
        hdc_charge_time=excluded.hdc_charge_time, hdc_charge_dist=excluded.hdc_charge_dist,
        hdc_eco_time=excluded.hdc_eco_time, hdc_eco_dist=excluded.hdc_eco_dist,
        hdc_power_time=excluded.hdc_power_time, hdc_power_dist=excluded.hdc_power_dist,
        behaviours_json=excluded.behaviours_json, route_json=excluded.route_json,
        imported_at=datetime('now')
"""


def _get_db() -> sqlite3.Connection:
    return _get_db_raw("trips")


def _q(name: str) -> str:
    return load_queries("trips")[name]


def _trip_to_row(trip: dict[str, Any], vin: str | None = "") -> tuple:
    s = trip.get("summary", {})
    scores = trip.get("scores", {})
    hdc = trip.get("hdc", {})
    return (
        trip.get("id"),
        vin or "",
        trip.get("category"),
        s.get("startTs"),
        s.get("endTs"),
        s.get("length"),
        s.get("duration"),
        s.get("durationIdle"),
        s.get("maxSpeed"),
        s.get("averageSpeed"),
        s.get("fuelConsumption"),
        s.get("startLat"),
        s.get("startLon"),
        s.get("endLat"),
        s.get("endLon"),
        1 if s.get("nightTrip") else 0,
        s.get("lengthOverspeed"),
        s.get("durationOverspeed"),
        s.get("lengthHighway"),
        s.get("durationHighway"),
        json.dumps(s.get("countries", [])),
        scores.get("global"),
        scores.get("acceleration"),
        scores.get("braking"),
        scores.get("constantSpeed"),
        scores.get("advice"),
        hdc.get("evTime"),
        hdc.get("evDistance"),
        hdc.get("chargeTime"),
        hdc.get("chargeDist"),
        hdc.get("ecoTime"),
        hdc.get("ecoDist"),
        hdc.get("powerTime"),
        hdc.get("powerDist"),
        json.dumps(trip.get("behaviours", [])),
        json.dumps(trip.get("route", [])),
    )


def upsert_trips(trips: list[dict[str, Any]], vin: str | None = "") -> tuple[int, int]:
    """Bulk upsert trips. Returns (new_count, updated_count)."""
    conn = _get_db()
    new = 0
    updated = 0
    for trip in trips:
        existing = conn.execute(_q("upsert_check"), (trip.get("id"),)).fetchone()
        conn.execute(_UPSERT_SQL, _trip_to_row(trip, vin))
        if existing:
            updated += 1
        else:
            new += 1
    conn.commit()
    conn.close()
    return new, updated


def get_latest_trip_timestamp() -> str | None:
    """Get the start_ts of the newest trip in the DB."""
    conn = _get_db()
    row = conn.execute(_q("latest_timestamp")).fetchone()
    conn.close()
    return row[0] if row else None


def get_trip_count() -> int:
    conn = _get_db()
    count = conn.execute(_q("trip_count")).fetchone()[0]
    conn.close()
    return count


def get_trips_from_db(
    limit: int = 50,
    offset: int = 0,
    from_date: str | None = None,
    to_date: str | None = None,
    vin: str | None = None,
) -> list[dict]:
    """Query trips from local DB with optional filters."""
    conn = _get_db()
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM trips WHERE 1=1"
    params = []
    if vin:
        sql += " AND vin = ?"
        params.append(vin)
    if from_date:
        sql += " AND start_ts >= ?"
        params.append(from_date)
    if to_date:
        sql += " AND start_ts <= ?"
        params.append(to_date + "T23:59:59Z")
    sql += " ORDER BY start_ts DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        ev_d = d.get("hdc_ev_distance") or 0
        if ev_d > 0 and d.get("avg_speed"):
            reku_pct = (d.get("hdc_charge_dist") or 0) / ev_d * 100
            power_pct = (d.get("hdc_power_dist") or 0) / ev_d * 100
            d["est_kwh_100km"] = round(estimate_kwh_100km(d["avg_speed"], reku_pct, power_pct), 1)
        else:
            d["est_kwh_100km"] = None
        result.append(d)
    return result
