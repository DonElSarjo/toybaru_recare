"""Charge-session storage - CRUD for the charges database (NA charge history).

Mirrors trip_store: sessions are fetched from the API on demand (a Sync action),
upserted idempotently (keyed on vin+start_time so re-syncing never duplicates),
and the UI reads from here rather than hitting the API on every view.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from toybaru.database import get_db as _get_db_raw, load_queries

_UPSERT_SQL = """
    INSERT INTO charge_sessions (
        vin, start_time, end_time, soc_before, soc_after, total_kwhr,
        location_type, address, latitude, longitude, watttime_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(vin, start_time) DO UPDATE SET
        end_time=excluded.end_time,
        soc_before=excluded.soc_before,
        soc_after=excluded.soc_after,
        total_kwhr=excluded.total_kwhr,
        location_type=excluded.location_type,
        address=excluded.address,
        latitude=excluded.latitude,
        longitude=excluded.longitude,
        watttime_json=excluded.watttime_json,
        imported_at=datetime('now')
"""


def _get_db() -> sqlite3.Connection:
    return _get_db_raw("charges")


def _q(name: str) -> str:
    return load_queries("charges")[name]


def _str(v: Any) -> str | None:
    """Preserve the API's representation (values may carry units like '%')."""
    return None if v is None else str(v)


def _session_to_row(s: dict[str, Any], vin: str | None = "") -> tuple:
    wt = s.get("watttime_details")
    return (
        vin or "",
        _str(s.get("start_time")),
        _str(s.get("end_time")),
        _str(s.get("soc_before_charging")),
        _str(s.get("soc_after_charging")),
        _str(s.get("total_charge_kwhr")),
        s.get("charge_location_type"),
        s.get("address"),
        s.get("latitude"),
        s.get("longitude"),
        json.dumps(wt) if wt is not None else None,
    )


def upsert_charges(sessions: list[dict[str, Any]], vin: str | None = "") -> tuple[int, int]:
    """Bulk upsert charge sessions. Returns (new_count, updated_count).

    Sessions without a start_time can't be keyed and are skipped."""
    conn = _get_db()
    new = updated = 0
    try:
        for s in sessions:
            start = s.get("start_time")
            if start is None:
                continue
            existing = conn.execute(_q("upsert_check"), (vin or "", str(start))).fetchone()
            conn.execute(_UPSERT_SQL, _session_to_row(s, vin))
            if existing:
                updated += 1
            else:
                new += 1
        conn.commit()
    finally:
        conn.close()
    return new, updated


def get_charge_count() -> int:
    conn = _get_db()
    try:
        return conn.execute(_q("charge_count")).fetchone()[0]
    finally:
        conn.close()


def get_latest_charge_timestamp() -> str | None:
    conn = _get_db()
    try:
        row = conn.execute(_q("latest_timestamp")).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_charges_from_db(
    limit: int = 200,
    offset: int = 0,
    vin: str | None = None,
) -> list[dict]:
    """Return stored charge sessions (newest first) with API-shaped keys, so the
    UI renderer is identical to the live shape."""
    conn = _get_db()
    conn.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM charge_sessions WHERE 1=1"
        params: list[Any] = []
        if vin:
            sql += " AND vin = ?"
            params.append(vin)
        sql += " ORDER BY start_time DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        out.append({
            "start_time": d.get("start_time"),
            "end_time": d.get("end_time"),
            "soc_before_charging": d.get("soc_before"),
            "soc_after_charging": d.get("soc_after"),
            "total_charge_kwhr": d.get("total_kwhr"),
            "charge_location_type": d.get("location_type"),
            "address": d.get("address"),
            "latitude": d.get("latitude"),
            "longitude": d.get("longitude"),
            "watttime_details": json.loads(d["watttime_json"]) if d.get("watttime_json") else None,
        })
    return out
