"""Toybaru ReCare - Web Dashboard."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
from datetime import date, timedelta
from pathlib import Path
from secrets import token_hex
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from toybaru.client import ToybaruClient
from toybaru.const import DATA_DIR, REGIONS, BRANDS
from toybaru.exceptions import OtpRequiredError
from toybaru.soc_tracker import log_snapshot, get_consumption_estimate, get_snapshot_history
from toybaru.trip_store import (
    upsert_trips, get_trip_count, get_trips_from_db,
    get_latest_trip_timestamp,
)
from toybaru.trip_stats import get_detailed_stats, get_stats

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
LOCALES_DIR = Path(__file__).parent / "locales"
CREDS_FILE = DATA_DIR / "credentials.json"
META_FILE = DATA_DIR / "session_meta.json"
SESSION_SECRET = os.environ.get("TOYBARU_SESSION_SECRET", secrets.token_hex(32))

app = FastAPI(title="Toybaru ReCare")

# Session store: token -> ToybaruClient
_sessions: dict[str, ToybaruClient] = {}
_csrf_tokens: dict[str, str] = {}
_otp_pending: dict[str, dict] = {}


def _get_session_client(session_token: str | None) -> ToybaruClient | None:
    if not session_token:
        return None
    return _sessions.get(session_token)


def _require_csrf(request: Request, session: str | None) -> None:
    """Validate X-CSRF-Token header against session."""
    if not session or session not in _csrf_tokens:
        raise HTTPException(status_code=403, detail="Missing CSRF token")
    expected = _csrf_tokens[session]
    actual = request.headers.get("X-CSRF-Token", "")
    if actual != expected:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


async def _require_client(session_token: str | None) -> ToybaruClient:
    client = _get_session_client(session_token)
    if client is None:
        # Try loading from saved tokens + session_meta.json
        if META_FILE.exists():
            try:
                meta = json.loads(META_FILE.read_text())
                from toybaru.auth.controller import TOKEN_FILE
                if TOKEN_FILE.exists():
                    # We have tokens on disk — try to restore
                    # We need username/password but meta doesn't store password
                    # Just create client with dummy password — tokens will load from disk
                    client = ToybaruClient(
                        username=meta["username"],
                        password="",
                        region=meta.get("region", "subaru-eu"),
                    )
                    if client.auth.is_authenticated:
                        token = session_token or secrets.token_hex(32)
                        _sessions[token] = client
                        return client
            except Exception:
                pass
        # Legacy: try credentials.json
        if CREDS_FILE.exists():
            try:
                creds = json.loads(CREDS_FILE.read_text())
                client = ToybaruClient(
                    username=creds["username"],
                    password=creds.get("password", ""),
                    region=creds.get("region", "subaru-eu"),
                )
                await client.login()
                token = session_token or secrets.token_hex(32)
                _sessions[token] = client
                return client
            except Exception:
                pass
        raise HTTPException(status_code=401, detail="Not authenticated")
    return client


async def safe_call(coro):
    try:
        return await coro
    except Exception as e:
        logger.exception("API call failed")
        return {"error": "An error occurred"}


# --- Pages ---

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=(TEMPLATES_DIR / "dashboard.html").read_text())


@app.get("/api/brands")
async def api_brands():
    """Return brand -> region mapping for the login UI."""
    result = {}
    for brand_key, brand_info in BRANDS.items():
        result[brand_key] = {
            "label": brand_info["label"],
            "regions": [{"key": r, "name": REGIONS[r].name} for r in brand_info["regions"] if r in REGIONS],
        }
    return result


@app.get("/api/languages")
async def api_languages():
    """List all available languages by scanning locale files."""
    langs = []
    for f in sorted(LOCALES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            meta = data.get("_meta", {})
            langs.append({"code": f.stem, "label": meta.get("label", f.stem), "locale": meta.get("locale", f.stem)})
        except Exception:
            pass
    return langs


@app.get("/api/locale/{lang}")
async def api_locale(lang: str):
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        path = LOCALES_DIR / "en.json"
    return JSONResponse(json.loads(path.read_text()))


# --- Auth ---

@app.post("/api/login")
async def api_login(request: Request, response: Response):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    region = body.get("region", "EU")

    if not username or not password:
        return JSONResponse({"error": "Missing credentials"}, status_code=400)

    try:
        client = ToybaruClient(username=username, password=password, region=region)
        uuid = await client.login()
        vehicles = await client.get_vehicles()
    except OtpRequiredError:
        # OTP required — save state for second phase
        otp_session = secrets.token_hex(16)
        _otp_pending[otp_session] = {
            "client": client,
            "username": username,
            "region": region,
        }
        return JSONResponse({
            "needs_otp": True,
            "otp_session": otp_session,
        })
    except Exception as e:
        logger.exception("Login failed")
        return JSONResponse({"error": "Authentication failed"}, status_code=401)

    # Create session
    token = secrets.token_hex(32)
    _sessions[token] = client

    # Generate CSRF token
    csrf = secrets.token_hex(16)
    _csrf_tokens[token] = csrf

    # Save only username+region (NO password)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps({
        "username": username,
        "region": region,
    }))

    response.set_cookie("session", token, httponly=True, samesite="strict", max_age=86400 * 30)
    return {
        "uuid": uuid,
        "vehicles": [v.model_dump() for v in vehicles],
        "csrf_token": csrf,
    }


@app.post("/api/login/otp")
async def api_login_otp(request: Request, response: Response):
    """Second phase of OTP login flow."""
    body = await request.json()
    otp_session = body.get("otp_session", "")
    code = body.get("code", "")

    if not otp_session or not code:
        return JSONResponse({"error": "Missing otp_session or code"}, status_code=400)

    pending = _otp_pending.pop(otp_session, None)
    if not pending:
        return JSONResponse({"error": "OTP session expired or invalid"}, status_code=400)

    client = pending["client"]
    try:
        uuid = await client.submit_otp(code)
        vehicles = await client.get_vehicles()
    except Exception as e:
        logger.exception("OTP verification failed")
        return JSONResponse({"error": "OTP verification failed"}, status_code=401)

    token = secrets.token_hex(32)
    _sessions[token] = client

    csrf = secrets.token_hex(16)
    _csrf_tokens[token] = csrf

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps({
        "username": pending["username"],
        "region": pending["region"],
    }))

    response.set_cookie("session", token, httponly=True, samesite="strict", max_age=86400 * 30)
    return {
        "uuid": uuid,
        "vehicles": [v.model_dump() for v in vehicles],
        "csrf_token": csrf,
    }


@app.get("/api/auth/status")
async def api_auth_status(session: str | None = Cookie(None)):
    client = _get_session_client(session)
    if client:
        csrf = _csrf_tokens.get(session, "")
        return {"authenticated": True, "csrf_token": csrf}
    # Try saved creds
    if META_FILE.exists() or CREDS_FILE.exists():
        try:
            client = await _require_client(session)
            return {"authenticated": True}
        except Exception:
            pass
    return {"authenticated": False}


@app.post("/api/logout")
async def api_logout(response: Response, session: str | None = Cookie(None)):
    if session and session in _sessions:
        del _sessions[session]
    if session and session in _csrf_tokens:
        del _csrf_tokens[session]
    response.delete_cookie("session")
    from toybaru.auth.controller import TOKEN_FILE
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
    if META_FILE.exists():
        META_FILE.unlink()
    if CREDS_FILE.exists():
        CREDS_FILE.unlink()
    return {"ok": True}


# --- Vehicle API ---

@app.get("/api/vehicles")
async def api_vehicles(session: str | None = Cookie(None)):
    client = await _require_client(session)
    vehicles = await client.get_vehicles()
    return [v.model_dump() for v in vehicles]


@app.get("/api/all/{vin}")
async def api_all(vin: str, session: str | None = Cookie(None)):
    client = await _require_client(session)
    battery = await safe_call(client.get_electric_status(vin))
    telemetry = await safe_call(client.get_telemetry(vin))
    status = await safe_call(client.get_vehicle_status(vin))
    location = await safe_call(client.get_location(vin))

    if isinstance(battery, dict) and "error" not in battery:
        loc = location.get("vehicleLocation", {}) if isinstance(location, dict) else {}
        log_snapshot(
            vin=vin,
            soc=battery.get("batteryLevel"),
            range_km=battery.get("evRange", {}).get("value") if isinstance(battery.get("evRange"), dict) else None,
            range_ac_km=battery.get("evRangeWithAc", {}).get("value") if isinstance(battery.get("evRangeWithAc"), dict) else None,
            odometer=telemetry.get("odometer", {}).get("value") if isinstance(telemetry, dict) and isinstance(telemetry.get("odometer"), dict) else None,
            charging_status=battery.get("chargingStatus"),
            latitude=loc.get("latitude"),
            longitude=loc.get("longitude"),
        )

    return {
        "status": status,
        "battery": battery,
        "location": location,
        "telemetry": telemetry,
        "consumption": get_consumption_estimate(),
        "capabilities": {"trips": not client.api._is_na},
    }


@app.get("/api/battery/{vin}")
async def api_battery(vin: str, session: str | None = Cookie(None)):
    client = await _require_client(session)
    return await safe_call(client.get_electric_status(vin))


@app.post("/api/refresh/{vin}")
async def api_refresh(vin: str, request: Request, session: str | None = Cookie(None)):
    _require_csrf(request, session)
    client = await _require_client(session)
    return await safe_call(client.refresh_status(vin))


@app.post("/api/command/{vin}/{command}")
async def api_command(vin: str, command: str, request: Request, session: str | None = Cookie(None)):
    """Send remote command."""
    allowed = {
        "door-lock", "door-unlock",
        "trunk-lock", "trunk-unlock",
        "headlight-on", "headlight-off",
        "sound-horn", "buzzer-warning",
        "find-vehicle",
        "hazard-on", "hazard-off",
        "engine-start", "engine-stop",
    }
    if command not in allowed:
        return JSONResponse({"error": f"Unknown command: {command}"}, status_code=400)
    _require_csrf(request, session)
    client = await _require_client(session)
    return await safe_call(client.send_command(vin, command))


@app.post("/api/sync/{vin}")
async def api_sync(vin: str, request: Request, session: str | None = Cookie(None)):
    _require_csrf(request, session)
    client = await _require_client(session)
    latest = get_latest_trip_timestamp()
    from_date = latest[:10] if latest else "2020-01-01"

    total_new = 0
    total_updated = 0
    offset = 0
    while True:
        try:
            data = await client.get_trips(
                vin, from_date=date.fromisoformat(from_date), to_date=date.today(),
                route=True, summary=True, limit=5, offset=offset,
            )
        except Exception as e:
            logger.exception("Sync fetch error")
            return {"error": "Failed to sync trips", "new": total_new, "updated": total_updated}

        payload = data.get("payload", data)
        trips = payload.get("trips", [])
        if not trips:
            break

        new, updated = upsert_trips(trips, vin=vin)
        total_new += new
        total_updated += updated

        meta = payload.get("_metadata", {}).get("pagination", {})
        next_offset = meta.get("nextOffset")
        if next_offset is None or next_offset <= offset:
            break
        offset = next_offset

    return {"new": total_new, "updated": total_updated, "db_total": get_trip_count()}


@app.get("/api/trips/{vin}")
async def api_trips(vin: str, days: int = 30, session: str | None = Cookie(None)):
    client = await _require_client(session)
    return await safe_call(client.get_trips(
        vin, from_date=date.today() - timedelta(days=days), to_date=date.today(),
        route=False, summary=True, limit=50,
    ))


# --- Local DB ---

@app.get("/api/db/trips")
async def api_db_trips(limit: int = 50, offset: int = 0, from_date: str | None = None, to_date: str | None = None, vin: str | None = None, session: str | None = Cookie(None)):
    await _require_client(session)
    return get_trips_from_db(limit=limit, offset=offset, from_date=from_date, to_date=to_date, vin=vin)


@app.get("/api/db/stats")
async def api_db_stats(vin: str | None = None, from_date: str | None = None, to_date: str | None = None, session: str | None = Cookie(None)):
    await _require_client(session)
    return get_detailed_stats(vin=vin, from_date=from_date, to_date=to_date)


@app.get("/api/db/count")
async def api_db_count(session: str | None = Cookie(None)):
    await _require_client(session)
    return {"count": get_trip_count()}


@app.get("/api/db/trip/{trip_id}")
async def api_db_trip(trip_id: str, session: str | None = Cookie(None)):
    await _require_client(session)
    import sqlite3
    from toybaru.trip_store import _get_db
    conn = _get_db()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["behaviours"] = json.loads(d.get("behaviours_json") or "[]")
        d["route"] = json.loads(d.get("route_json") or "[]")
        return d
    return {"error": "Trip not found"}


# --- Import with SSE ---

@app.get("/api/import/{vin}")
async def api_import(vin: str, from_date: str = "2020-01-01", to_date: str | None = None, session: str | None = Cookie(None)):
    if to_date is None:
        to_date = str(date.today())

    async def event_stream():
        client = await _require_client(session)
        offset = 0
        total_new = 0
        total_updated = 0
        total_fetched = 0

        yield f"data: {json.dumps({'type': 'start', 'from': from_date, 'to': to_date})}\n\n"

        while True:
            try:
                data = await client.get_trips(
                    vin, from_date=date.fromisoformat(from_date), to_date=date.fromisoformat(to_date),
                    route=True, summary=True, limit=5, offset=offset,
                )
            except Exception as e:
                logger.exception("Import fetch error")
                yield f"data: {json.dumps({'type': 'error', 'message': 'Failed to fetch trips'})}\n\n"
                break

            payload = data.get("payload", data)
            trips = payload.get("trips", [])
            meta = payload.get("_metadata", {}).get("pagination", {})
            total_count = meta.get("totalCount", 0)

            if not trips:
                break

            new, updated = upsert_trips(trips, vin=vin)
            total_new += new
            total_updated += updated
            total_fetched += len(trips)

            pct = round(total_fetched / total_count * 100) if total_count else 0
            batch_info = [{"date": tr.get("summary",{}).get("startTs","")[:10], "km": round(tr.get("summary",{}).get("length",0)/1000,1), "spd": round(tr.get("summary",{}).get("averageSpeed",0)), "score": tr.get("scores",{}).get("global")} for tr in trips]
            yield f"data: {json.dumps({'type': 'progress', 'fetched': total_fetched, 'total': total_count, 'new': total_new, 'updated': total_updated, 'pct': pct, 'trips': batch_info})}\n\n"

            next_offset = meta.get("nextOffset")
            if next_offset is None or next_offset <= offset:
                break
            offset = next_offset
            await asyncio.sleep(0.1)

        yield f"data: {json.dumps({'type': 'done', 'fetched': total_fetched, 'new': total_new, 'updated': total_updated, 'db_total': get_trip_count()})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Export ---

@app.get("/api/export/trips.csv")
async def export_trips_csv(vin: str | None = None, session: str | None = Cookie(None)):
    """Export all trips as CSV download."""
    await _require_client(session)
    import csv
    import io
    from toybaru.database import get_db as _open_db
    import sqlite3

    conn = _open_db("trips")
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM trips"
    params = []
    if vin:
        sql += " WHERE vin = ?"
        params.append(vin)
    sql += " ORDER BY start_ts"
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    buf = io.StringIO()
    if rows:
        cols = [k for k in rows[0].keys() if k not in ('behaviours_json', 'route_json', 'raw_json')]
        writer = csv.DictWriter(buf, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] for k in cols})

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=toybaru_trips.csv"},
    )


@app.get("/api/export/snapshots.csv")
async def export_snapshots_csv(vin: str | None = None, session: str | None = Cookie(None)):
    """Export all snapshots as CSV download."""
    await _require_client(session)
    import csv
    import io
    from toybaru.database import get_db as _open_db
    import sqlite3

    conn = _open_db("snapshots")
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM snapshots"
    params = []
    if vin:
        sql += " WHERE vin = ?"
        params.append(vin)
    sql += " ORDER BY timestamp"
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=toybaru_snapshots.csv"},
    )


@app.get("/api/export/trips.json")
async def export_trips_json(vin: str | None = None, session: str | None = Cookie(None)):
    """Export all trips as JSON download (including behaviours and route)."""
    await _require_client(session)
    from toybaru.database import get_db as _open_db
    import sqlite3

    conn = _open_db("trips")
    conn.row_factory = sqlite3.Row
    sql = "SELECT * FROM trips"
    params = []
    if vin:
        sql += " WHERE vin = ?"
        params.append(vin)
    sql += " ORDER BY start_ts"
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    trips = []
    for r in rows:
        d = dict(r)
        d["behaviours"] = json.loads(d.pop("behaviours_json", "[]") or "[]")
        d["route"] = json.loads(d.pop("route_json", "[]") or "[]")
        d.pop("raw_json", None)
        trips.append(d)

    return Response(
        content=json.dumps(trips, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=toybaru_trips.json"},
    )


# --- Re-Import ---

@app.post("/api/reimport")
async def api_reimport(request: Request, session: str | None = Cookie(None)):
    """Re-import trips from a previously exported JSON file."""
    _require_csrf(request, session)
    await _require_client(session)
    body = await request.json()
    trips = body.get("trips", [])
    if not trips:
        return JSONResponse({"error": "No trips in data"}, status_code=400)

    # Convert from export format back to API format for upsert
    converted = []
    for tr in trips:
        trip = {
            "id": tr.get("id"),
            "category": tr.get("category"),
            "summary": {
                "startTs": tr.get("start_ts"),
                "endTs": tr.get("end_ts"),
                "length": tr.get("length_m"),
                "duration": tr.get("duration_s"),
                "durationIdle": tr.get("duration_idle_s"),
                "maxSpeed": tr.get("max_speed"),
                "averageSpeed": tr.get("avg_speed"),
                "fuelConsumption": tr.get("fuel_consumption"),
                "startLat": tr.get("start_lat"),
                "startLon": tr.get("start_lon"),
                "endLat": tr.get("end_lat"),
                "endLon": tr.get("end_lon"),
                "nightTrip": bool(tr.get("night_trip")),
                "lengthOverspeed": tr.get("length_overspeed"),
                "durationOverspeed": tr.get("duration_overspeed"),
                "lengthHighway": tr.get("length_highway"),
                "durationHighway": tr.get("duration_highway"),
                "countries": json.loads(tr.get("countries", "[]")) if isinstance(tr.get("countries"), str) else tr.get("countries", []),
            },
            "scores": {
                "global": tr.get("score_global"),
                "acceleration": tr.get("score_acceleration"),
                "braking": tr.get("score_braking"),
                "constantSpeed": tr.get("score_constant_speed"),
                "advice": tr.get("score_advice"),
            },
            "hdc": {
                "evTime": tr.get("hdc_ev_time"),
                "evDistance": tr.get("hdc_ev_distance"),
                "chargeTime": tr.get("hdc_charge_time"),
                "chargeDist": tr.get("hdc_charge_dist"),
                "ecoTime": tr.get("hdc_eco_time"),
                "ecoDist": tr.get("hdc_eco_dist"),
                "powerTime": tr.get("hdc_power_time"),
                "powerDist": tr.get("hdc_power_dist"),
            },
            "behaviours": tr.get("behaviours", []),
            "route": tr.get("route", []),
        }
        converted.append(trip)

    vin = trips[0].get("vin") if trips else None
    new, updated = upsert_trips(converted, vin=vin)
    return {"new": new, "updated": updated, "total": get_trip_count()}


# --- Route SVG ---

@app.get("/api/route-svg/{trip_id}")
async def api_route_svg(trip_id: str, width: int = 800, height: int = 500, session: str | None = Cookie(None)):
    await _require_client(session)
    import sqlite3
    from toybaru.database import get_db as _open_db

    conn = _open_db("trips")
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT route_json, behaviours_json FROM trips WHERE id = ?", (trip_id,)).fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error": "Trip not found"}, status_code=404)

    route = json.loads(row["route_json"] or "[]")
    behaviours = json.loads(row["behaviours_json"] or "[]")
    pts = [p for p in route if p.get("lat") and p.get("lon")]
    if not pts:
        return JSONResponse({"error": "No route data"}, status_code=404)

    lats = [p["lat"] for p in pts]
    lons = [p["lon"] for p in pts]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    pad_lat = (max_lat - min_lat) * 0.05 or 0.001
    pad_lon = (max_lon - min_lon) * 0.05 or 0.001
    min_lat -= pad_lat; max_lat += pad_lat
    min_lon -= pad_lon; max_lon += pad_lon

    def proj(lat, lon):
        x = (lon - min_lon) / (max_lon - min_lon) * width
        y = (1 - (lat - min_lat) / (max_lat - min_lat)) * height
        return x, y

    mode_colors = {0: "#58a6ff", 1: "#3fb950", 2: "#f85149"}
    svg_parts = []
    seg = [pts[0]]
    prev_mode = pts[0].get("mode", 1)
    for p in pts[1:]:
        m = p.get("mode", 1)
        if m != prev_mode and len(seg) > 1:
            d = "M" + " L".join(f"{proj(s['lat'],s['lon'])[0]:.1f},{proj(s['lat'],s['lon'])[1]:.1f}" for s in seg)
            svg_parts.append(f'<path d="{d}" stroke="{mode_colors.get(prev_mode, "#8b949e")}" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>')
            seg = [seg[-1]]
            prev_mode = m
        seg.append(p)
    if len(seg) > 1:
        d = "M" + " L".join(f"{proj(s['lat'],s['lon'])[0]:.1f},{proj(s['lat'],s['lon'])[1]:.1f}" for s in seg)
        svg_parts.append(f'<path d="{d}" stroke="{mode_colors.get(prev_mode, "#8b949e")}" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>')

    sx, sy = proj(pts[0]["lat"], pts[0]["lon"])
    ex, ey = proj(pts[-1]["lat"], pts[-1]["lon"])
    svg_parts.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="6" fill="#3fb950" stroke="#0d1117" stroke-width="2"/>')
    svg_parts.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="6" fill="#f85149" stroke="#0d1117" stroke-width="2"/>')

    for b in behaviours:
        if not b.get("lat") or not b.get("lon"):
            continue
        bx, by = proj(b["lat"], b["lon"])
        color = "#3fb950" if b.get("good") else ("#f85149" if b.get("type") == "B" else "#d29922")
        svg_parts.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="4" fill="{color}" stroke="#0d1117" stroke-width="1.5" opacity="0.9"/>')

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">{"".join(svg_parts)}</svg>'
    return {
        "svg": svg,
        "bounds": [[min_lat, min_lon], [max_lat, max_lon]],
        "point_count": len(pts),
        "behaviour_count": len([b for b in behaviours if b.get("lat")]),
    }


# --- Raw API proxy ---

@app.get("/api/raw/{path:path}")
async def api_raw(path: str, vin: str | None = None, session: str | None = Cookie(None)):
    client = await _require_client(session)
    endpoint = f"/{path}" if not path.startswith("/") else path
    return await safe_call(client.raw_request("GET", endpoint, vin=vin))


def run(host: str = "127.0.0.1", port: int = 8099):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
