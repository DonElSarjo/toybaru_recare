"""Snapshot tracker - logs vehicle state over time for consumption analysis."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from toybaru.database import get_db as _get_db_raw

logger = logging.getLogger(__name__)

BATTERY_CAPACITY_KWH = 71.4


def _get_db() -> sqlite3.Connection:
    return _get_db_raw("snapshots")


def log_snapshot(
    vin: str | None = None,
    soc: int | None = None,
    range_km: float | None = None,
    range_ac_km: float | None = None,
    odometer: float | None = None,
    charging_status: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> None:
    """Log a vehicle state snapshot. Skips if nothing changed since last entry."""
    if soc is None:
        return
    # Normalize charging_status to match DB constraint
    _cs_map = {"not connected": "none", "not_connected": "none"}
    if charging_status:
        charging_status = _cs_map.get(charging_status.lower(), charging_status.lower())
        if charging_status not in ("none", "charging", "connected"):
            charging_status = None
    # Snapshot logging is fire-and-forget telemetry: a non-writable DATA_DIR
    # (e.g. a misowned container volume) must not 500 the dashboard. Degrade
    # gracefully with a warning instead.
    try:
        conn = _get_db()
        try:
            last = conn.execute(
                "SELECT soc, odometer FROM snapshots WHERE vin = ? ORDER BY timestamp DESC LIMIT 1",
                (vin,),
            ).fetchone()
            if last and last[0] == soc and last[1] == odometer:
                return
            ts = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO snapshots (vin, timestamp, soc, range_km, range_ac_km, odometer, charging_status, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (vin, ts, soc, range_km, range_ac_km, odometer, charging_status, latitude, longitude),
            )
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as e:
        logger.warning("Could not write snapshot (%s); check DATA_DIR is writable.", e)


def get_consumption_estimate() -> dict[str, Any]:
    """Calculate kWh/100km from snapshot pairs where car was driven."""
    try:
        conn = _get_db()
        try:
            rows = conn.execute(
                "SELECT timestamp, soc, range_km, odometer FROM snapshots ORDER BY timestamp ASC"
            ).fetchall()
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as e:
        logger.warning("Could not read snapshots (%s); check DATA_DIR is writable.", e)
        return {"entries": 0, "kwh_per_100km": None, "message": "Snapshot data unavailable."}

    if len(rows) < 2:
        return {"entries": len(rows), "kwh_per_100km": None, "message": "Zu wenig Datenpunkte."}

    segments = []
    for i in range(1, len(rows)):
        _, soc_prev, _, odo_prev = rows[i - 1]
        _, soc_curr, _, odo_curr = rows[i]
        if odo_prev is None or odo_curr is None or soc_prev is None or soc_curr is None:
            continue
        delta_km = odo_curr - odo_prev
        delta_soc = soc_prev - soc_curr
        if delta_km > 1 and delta_soc > 0:
            kwh_used = (delta_soc / 100) * BATTERY_CAPACITY_KWH
            kwh_per_100km = kwh_used / delta_km * 100
            if 5 <= kwh_per_100km <= 50:
                segments.append({"delta_km": round(delta_km, 1), "kwh_used": round(kwh_used, 2), "kwh_per_100km": round(kwh_per_100km, 1)})

    if not segments:
        return {"entries": len(rows), "segments": 0, "kwh_per_100km": None, "message": "Noch keine Fahrsegmente."}

    total_km = sum(s["delta_km"] for s in segments)
    total_kwh = sum(s["kwh_used"] for s in segments)
    return {
        "entries": len(rows),
        "segments": len(segments),
        "total_km": round(total_km, 1),
        "kwh_per_100km": round(total_kwh / total_km * 100, 1) if total_km > 0 else None,
    }


def get_snapshot_history(limit: int = 100) -> list[dict]:
    try:
        conn = _get_db()
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM snapshots ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        finally:
            conn.close()
    except (sqlite3.Error, OSError) as e:
        logger.warning("Could not read snapshot history (%s); check DATA_DIR is writable.", e)
        return []
    return [dict(r) for r in reversed(rows)]
