"""Trip statistics and consumption estimation for the dashboard."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from toybaru.database import get_db as _get_db_raw, load_queries


def _get_db() -> sqlite3.Connection:
    return _get_db_raw("trips")


def _q(name: str) -> str:
    return load_queries("trips")[name]


def estimate_kwh_100km(avg_speed: float, reku_pct: float, power_pct: float) -> float:
    """Estimate energy consumption in kWh/100km from trip characteristics."""
    v = max(avg_speed, 1)
    e_base = 10.0
    e_speed = 0.0013 * v * v
    e_regen = -(reku_pct / 100) * 5.0
    e_power = (power_pct / 100) * 5.0
    e_aux = 2.0 * (100 / v)
    return max(e_base + e_speed + e_regen + e_power + e_aux, 5.0)


def get_detailed_stats(vin: str | None = None, from_date: str | None = None, to_date: str | None = None) -> dict:
    """Comprehensive stats for the stats page."""
    conn = _get_db()
    w = "WHERE 1=1"
    p: list = []
    if vin:
        w += " AND vin = ?"; p.append(vin)
    if from_date:
        w += " AND start_ts >= ?"; p.append(from_date)
    if to_date:
        w += " AND start_ts <= ?"; p.append(to_date + "T23:59:59Z")

    def q(name: str) -> str:
        return _q(name).replace("{where}", w)

    ov = conn.execute(q("overview"), p).fetchone()

    if not ov or not ov[0]:
        conn.close()
        return {"total_trips": 0}

    total_trips, total_m, total_s, avg_spd, max_spd = ov[0], ov[1] or 0, ov[2] or 0, ov[3], ov[4]
    ev_d = ov[9] or 1

    monthly = conn.execute(q("monthly"), p).fetchall()
    weekday = conn.execute(q("weekday"), p).fetchall()
    hourly = conn.execute(q("hourly"), p).fetchall()
    speed_cats = conn.execute(q("speed_categories"), p).fetchone()
    score_dist = conn.execute(q("score_distribution"), p).fetchall()

    records = {}
    for label, query_name in [
        ("longest_trip", "record_longest"),
        ("fastest_avg", "record_fastest_avg"),
        ("best_score", "record_best_score"),
        ("best_reku", "record_best_reku"),
        ("top_speed", "record_top_speed"),
    ]:
        r = conn.execute(q(query_name), p).fetchone()
        if r:
            records[label] = {"id": r[0], "value": r[1], "date": r[2]}

    best_day = conn.execute(q("best_day"), p).fetchone()

    conn.close()

    days = max(1, round((datetime.fromisoformat(ov[7].replace('Z','')) - datetime.fromisoformat(ov[6].replace('Z',''))).days)) if ov[6] and ov[7] else 1

    return {
        "total_trips": total_trips,
        "total_km": round(total_m / 1000, 1),
        "total_hours": round(total_s / 3600, 1),
        "avg_speed": round(avg_spd, 1) if avg_spd else 0,
        "max_speed": max_spd,
        "avg_score": round(ov[5], 1) if ov[5] else 0,
        "avg_score_accel": round(ov[15], 1) if ov[15] else 0,
        "avg_score_braking": round(ov[16], 1) if ov[16] else 0,
        "avg_score_consistency": round(ov[17], 1) if ov[17] else 0,
        "first_trip": ov[6],
        "last_trip": ov[7],
        "days_span": days,
        "reku_pct": round(ov[8] / ev_d * 100, 1) if ev_d else 0,
        "eco_pct": round(ov[10] / ev_d * 100, 1) if ev_d else 0,
        "power_pct": round(ov[11] / ev_d * 100, 1) if ev_d else 0,
        "night_trips": ov[18],
        "night_pct": round(ov[18] / total_trips * 100, 1) if total_trips else 0,
        "overspeed_km": round((ov[19] or 0) / 1000, 1),
        "idle_hours": round((ov[12] or 0) / 3600, 1),
        "avg_trip_km": round(total_m / 1000 / total_trips, 1),
        "avg_trip_min": round(total_s / 60 / total_trips, 0),
        "trips_per_day": round(total_trips / days, 1),
        "km_per_day": round(total_m / 1000 / days, 1),
        "monthly": [{"month": r[0], "trips": r[1], "km": r[2], "speed": r[3], "score": r[4], "reku": r[5], "eco": r[6], "power": r[7]} for r in monthly],
        "weekday": [{"day": r[0], "trips": r[1], "km": r[2]} for r in weekday],
        "hourly": [{"hour": r[0], "trips": r[1], "km": r[2]} for r in hourly],
        "speed_cats": {
            "city_trips": speed_cats[0] or 0, "rural_trips": speed_cats[1] or 0, "highway_trips": speed_cats[2] or 0,
            "city_km": round((speed_cats[3] or 0) / 1000), "rural_km": round((speed_cats[4] or 0) / 1000), "highway_km": round((speed_cats[5] or 0) / 1000),
        },
        "score_dist": [{"bucket": f"{r[0]}-{r[0]+9}", "count": r[1]} for r in score_dist],
        "records": records,
        "best_day": {"date": best_day[0], "km": best_day[1], "trips": best_day[2]} if best_day else None,
        "est_avg_kwh_100km": round(estimate_kwh_100km(avg_spd or 50, ov[8]/ev_d*100 if ev_d else 20, ov[11]/ev_d*100 if ev_d else 20), 1) if avg_spd else None,
    }


def get_stats() -> dict:
    """Simple stats summary."""
    conn = _get_db()
    row = conn.execute(_q("simple_stats")).fetchone()
    conn.close()
    if not row or not row[0]:
        return {"total_trips": 0}
    return {
        "total_trips": row[0],
        "total_km": round(row[1] / 1000, 1) if row[1] else 0,
        "total_hours": round(row[2] / 3600, 1) if row[2] else 0,
        "avg_speed": round(row[3], 1) if row[3] else 0,
        "max_speed": row[4],
        "avg_score": round(row[5], 1) if row[5] else 0,
        "first_trip": row[6],
        "last_trip": row[7],
        "reku_pct": round(row[8] / row[9] * 100, 1) if row[9] else 0,
        "eco_pct": round(row[10] / row[9] * 100, 1) if row[9] else 0,
        "power_pct": round(row[11] / row[9] * 100, 1) if row[9] else 0,
        "est_avg_kwh_100km": round(estimate_kwh_100km(
            row[3] or 50,
            (row[8] / row[9] * 100) if row[9] else 20,
            (row[11] / row[9] * 100) if row[9] else 20,
        ), 1) if row[3] else None,
    }
