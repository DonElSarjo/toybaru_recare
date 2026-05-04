"""Toybaru ReCare - Web Dashboard."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import time
from datetime import date, timedelta
from pathlib import Path
from secrets import token_hex
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from toybaru.client import ToybaruClient
from toybaru.const import DATA_DIR, REGIONS, BRANDS, BRAND_LABELS
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

app = FastAPI(title="Toybaru ReCare")


# --- Security headers middleware (Fix 5) ---
class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

app.add_middleware(_SecurityHeadersMiddleware)


# --- Rate limiting (Fix 8) ---
class _RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int, max_keys: int = 10000):
        self._attempts: dict[str, list[float]] = {}
        self._max = max_attempts
        self._window = window_seconds
        self._max_keys = max_keys

    def check(self, key: str) -> bool:
        """Returns True if allowed, False if rate limited."""
        now = time.time()
        if len(self._attempts) > self._max_keys:
            self._cleanup(now)
        attempts = self._attempts.get(key, [])
        attempts = [t for t in attempts if now - t < self._window]
        if len(attempts) >= self._max:
            self._attempts[key] = attempts
            return False
        attempts.append(now)
        self._attempts[key] = attempts
        return True

    def _cleanup(self, now: float):
        self._attempts = {
            k: [t for t in v if now - t < self._window]
            for k, v in self._attempts.items()
            if any(now - t < self._window for t in v)
        }

_login_limiter = _RateLimiter(max_attempts=5, window_seconds=900)
_otp_limiter = _RateLimiter(max_attempts=5, window_seconds=300)
_command_limiter = _RateLimiter(max_attempts=20, window_seconds=60)


# --- Session store: token -> (ToybaruClient, created_at) (Fix 9) ---
_SESSION_MAX_AGE = 86400  # 24 hours
_OTP_MAX_AGE = 300  # 5 minutes

_sessions: dict[str, tuple[ToybaruClient, float]] = {}
_csrf_tokens: dict[str, str] = {}
_refresh_timestamps: dict[str, float] = {}  # per-VIN rate limiting
_otp_pending: dict[str, dict] = {}


def _get_session_client(session_token: str | None) -> ToybaruClient | None:
    if not session_token:
        return None
    entry = _sessions.get(session_token)
    if entry is None:
        return None
    client, created_at = entry
    if time.time() - created_at > _SESSION_MAX_AGE:
        # Session expired — force re-login
        _sessions.pop(session_token, None)
        _csrf_tokens.pop(session_token, None)
        return None
    return client


def _is_secure_request(request: Request) -> bool:
    """Determine if cookies should have the Secure flag."""
    if os.environ.get("TOYBARU_SECURE_COOKIES", "").lower() == "true":
        return True
    return request.headers.get("x-forwarded-proto") == "https"


def _validate_vin(vin: str) -> str:
    """Validate and normalize a VIN."""
    v = vin.upper()
    if not re.match(r'^[A-HJ-NPR-Z0-9]{17}$', v):
        raise HTTPException(status_code=400, detail="Invalid VIN format")
    return v


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
                    client = ToybaruClient(
                        username=meta["username"],
                        password="",
                        region=meta.get("region", "subaru-eu"),
                    )
                    if client.auth.is_authenticated:
                        token = session_token or secrets.token_hex(32)
                        _sessions[token] = (client, time.time())
                        return client
            except Exception:
                pass
        raise HTTPException(status_code=401, detail="Not authenticated")
    return client


def _write_meta_file(data: dict) -> None:
    """Write session_meta.json with restrictive permissions."""
    content = json.dumps(data)
    path = str(META_FILE)
    if os.name != "nt":
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, content.encode())
        finally:
            os.close(fd)
    else:
        META_FILE.write_text(content)


async def safe_call(coro):
    try:
        return await coro
    except Exception as e:
        logger.exception("API call failed")
        # Surface the actual upstream status so the UI can distinguish
        # rate-limits from real errors and render sensibly.
        from toybaru.exceptions import ApiError
        if isinstance(e, ApiError):
            return {"error": f"HTTP {e.status_code}", "status_code": e.status_code}
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


# --- Pages ---

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=(TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8"))


import re as _re
_CAR_SVG_PATH = TEMPLATES_DIR / "car-topdown.svg"
_HEX6_RE = _re.compile(r"^[0-9a-fA-F]{6}$")
_FILL_RE = _re.compile(r'fill="(#[0-9a-fA-F]{6})"')


def _tint_car_svg(svg: str, paint_hex: str) -> str:
    """Replace every light fill in the SVG with a paint-coloured equivalent.

    The Gemini car SVG uses ~50 slightly-different light grey shades (lum 175-255)
    to render the body with subtle shading. Dark shades (<175) are shadows,
    windows, tires — left untouched.

    Mapping: a fill with luminance ``lum`` blends toward ``paint_hex`` around
    a base luminance of 228 (the body's primary tone). Shades brighter than
    228 blend toward white; shades below blend toward a darker paint. This
    preserves the SVG's relative shading while recoloring the base.
    """
    pr = int(paint_hex[1:3], 16)
    pg = int(paint_hex[3:5], 16)
    pb = int(paint_hex[5:7], 16)
    BASE_LUM = 228  # #e6e5e0 — the Gemini body's dominant tone

    def _recolor(match: _re.Match) -> str:
        hx = match.group(1).lower()
        r = int(hx[1:3], 16)
        g = int(hx[3:5], 16)
        b = int(hx[5:7], 16)
        lum = (r + g + b) / 3
        if lum <= 175:
            return match.group(0)
        if lum >= BASE_LUM:
            # Lighten paint toward white by how much brighter this fill is than the body base.
            t = (lum - BASE_LUM) / (255 - BASE_LUM)
            nr = round(pr + (255 - pr) * t)
            ng = round(pg + (255 - pg) * t)
            nb = round(pb + (255 - pb) * t)
        else:
            # Subtle shading between paint-dark and paint-base (half-darken toward black).
            t = (BASE_LUM - lum) / (BASE_LUM - 175)
            nr = round(pr * (1 - 0.5 * t))
            ng = round(pg * (1 - 0.5 * t))
            nb = round(pb * (1 - 0.5 * t))
        return f'fill="#{nr:02x}{ng:02x}{nb:02x}"'

    return _FILL_RE.sub(_recolor, svg)


@app.get("/assets/car-topdown.svg")
async def car_topdown_svg(paint: str | None = None):
    """Top-down vehicle illustration. Optional `paint` query parameter (6-digit
    hex, no leading #) tints the body while leaving shadows/windows intact."""
    from fastapi.responses import Response
    svg = _CAR_SVG_PATH.read_text(encoding="utf-8")
    if paint and _HEX6_RE.match(paint):
        svg = _tint_car_svg(svg, "#" + paint.lower())
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


_ICONS_DIR = TEMPLATES_DIR / "icons"
_ICON_WHITELIST = {
    "favicon.ico":      "image/x-icon",
    "favicon-16.png":   "image/png",
    "favicon-32.png":   "image/png",
    "favicon-48.png":   "image/png",
    "favicon-180.png":  "image/png",
    "favicon-192.png":  "image/png",
    "favicon-512.png":  "image/png",
}


@app.get("/favicon.ico")
async def favicon_ico():
    from fastapi.responses import FileResponse
    return FileResponse(_ICONS_DIR / "favicon.ico", media_type="image/x-icon",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/assets/icons/{name}")
async def app_icon(name: str):
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    media = _ICON_WHITELIST.get(name)
    if not media:
        raise HTTPException(404, "icon not found")
    return FileResponse(_ICONS_DIR / name, media_type=media,
                        headers={"Cache-Control": "public, max-age=86400"})


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
            data = json.loads(f.read_text(encoding="utf-8"))
            meta = data.get("_meta", {})
            langs.append({"code": f.stem, "label": meta.get("label", f.stem), "locale": meta.get("locale", f.stem)})
        except Exception:
            pass
    return langs


@app.get("/api/locale/{lang}")
async def api_locale(lang: str):
    if not re.match(r'^[a-z]{2}(-[A-Za-z]{2,4})?$', lang):
        raise HTTPException(status_code=400, detail="Invalid locale")
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        # Try base language fallback (e.g. fr-CA → fr-FR → fr → en)
        base = lang.split("-")[0]
        candidates = sorted(LOCALES_DIR.glob(f"{base}*.json"))
        path = candidates[0] if candidates else LOCALES_DIR / "en.json"
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


# --- Auth ---

@app.post("/api/login")
async def api_login(request: Request, response: Response):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    region = body.get("region", "EU")

    if not username or not password:
        return JSONResponse({"error": "Missing credentials"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"
    if not _login_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Too many attempts")

    try:
        client = ToybaruClient(username=username, password=password, region=region)
        uuid = await client.login()
        vehicles = await client.get_vehicles()
    except OtpRequiredError:
        otp_session = secrets.token_hex(16)
        _otp_pending[otp_session] = {
            "client": client,
            "username": username,
            "region": region,
            "created_at": time.time(),
        }
        return JSONResponse({
            "needs_otp": True,
            "otp_session": otp_session,
        })
    except Exception as e:
        logger.exception("Login failed")
        return JSONResponse({"error": "Authentication failed"}, status_code=401)

    token = secrets.token_hex(32)
    _sessions[token] = (client, time.time())

    csrf = secrets.token_hex(16)
    _csrf_tokens[token] = csrf

    # Persisted meta never includes the password.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write_meta_file({"username": username, "region": region})

    secure = _is_secure_request(request)
    response.set_cookie("session", token, httponly=True, samesite="strict", max_age=86400 * 30, secure=secure)
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

    if time.time() - pending.get("created_at", 0) > _OTP_MAX_AGE:
        return JSONResponse({"error": "OTP session expired"}, status_code=400)

    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{client_ip}:{pending['username']}"
    if not _otp_limiter.check(rate_key):
        raise HTTPException(status_code=429, detail="Too many attempts")

    client = pending["client"]
    try:
        uuid = await client.submit_otp(code)
        vehicles = await client.get_vehicles()
    except Exception as e:
        logger.exception("OTP verification failed")
        return JSONResponse({"error": "OTP verification failed"}, status_code=401)

    token = secrets.token_hex(32)
    _sessions[token] = (client, time.time())

    csrf = secrets.token_hex(16)
    _csrf_tokens[token] = csrf

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _write_meta_file({"username": pending["username"], "region": pending["region"]})

    secure = _is_secure_request(request)
    response.set_cookie("session", token, httponly=True, samesite="strict", max_age=86400 * 30, secure=secure)
    return {
        "uuid": uuid,
        "vehicles": [v.model_dump() for v in vehicles],
        "csrf_token": csrf,
    }


@app.get("/api/auth/status")
async def api_auth_status(response: Response, session: str | None = Cookie(None)):
    client = _get_session_client(session)
    if client is None and META_FILE.exists():
        try:
            client = await _require_client(session)
        except Exception:
            client = None
    if client is None:
        return {"authenticated": False}
    # On server restart the cookie may not match an in-memory session yet;
    # re-anchor it so the next request finds the client.
    token = session if session in _sessions else next(
        (k for k, (c, _) in _sessions.items() if c is client), None
    )
    if token is None:
        token = secrets.token_hex(32)
        _sessions[token] = (client, time.time())
    if token not in _csrf_tokens:
        _csrf_tokens[token] = secrets.token_hex(16)
    if session != token:
        response.set_cookie("session", token, httponly=True, samesite="lax")
    return {"authenticated": True, "csrf_token": _csrf_tokens[token]}


@app.post("/api/logout")
async def api_logout(request: Request, response: Response, session: str | None = Cookie(None)):
    _require_csrf(request, session)
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
    vin = _validate_vin(vin)
    client = await _require_client(session)
    battery = await safe_call(client.get_electric_status(vin))
    telemetry = await safe_call(client.get_telemetry(vin))
    status = await safe_call(client.get_vehicle_status(vin))
    location = await safe_call(client.get_location(vin))

    vehicle_info: dict[str, Any] = {}
    cache_key = f"vehicle_info_{vin}"
    cached = getattr(client, "_cache", {}).get(cache_key)
    if cached:
        vehicle_info = cached
    else:
        try:
            vehicles = await client.get_vehicles()
            for v in vehicles:
                if v.vin and v.vin.upper() == vin.upper():
                    raw = v.model_dump(by_alias=True)
                    caps = raw.get("capabilities", [])
                    visible_caps = [
                        {"name": c.get("name"), "label": c.get("displayName") or c.get("name")}
                        for c in (caps if isinstance(caps, list) else [])
                        if c.get("display")
                    ]
                    subs_raw = raw.get("subscriptions", []) + raw.get("services", [])
                    subs = [
                        {
                            "name": s.get("displayProductName") or s.get("productName"),
                            "status": s.get("status"),
                            "type": s.get("type"),
                            "endDate": s.get("subscriptionEndDate"),
                            "daysRemaining": s.get("subscriptionRemainingDays"),
                        }
                        for s in (subs_raw if isinstance(subs_raw, list) else [])
                        if s.get("status") == "ACTIVE"
                    ]
                    rsc = raw.get("remoteServiceCapabilities") or {}
                    head_unit = raw.get("headUnit") or {}
                    dcm_info = raw.get("dcm") or {}
                    # `features` lists app-level features; `extendedCapabilities` lists hardware ones.
                    feat = raw.get("features") or {}
                    active_features = sorted(k for k, val in feat.items() if val == 1) if isinstance(feat, dict) else []
                    ext_caps = raw.get("extendedCapabilities") or {}
                    active_caps = sorted(k for k, val in ext_caps.items() if val is True) if isinstance(ext_caps, dict) else []

                    vehicle_info = {
                        "image": v.image,
                        "color": v.color,
                        "nickname": v.alias,
                        "model_name": v.model_name,
                        "model_year": v.model_year,
                        "capabilities": visible_caps,
                        "subscriptions": subs,
                        "manufactured_date": raw.get("manufacturedDate"),
                        "first_use_date": raw.get("dateOfFirstUse"),
                        "remote_capabilities": {
                            k: v for k, v in rsc.items()
                            if isinstance(v, bool) or isinstance(v, str)
                        } if rsc else {},
                        "head_unit": {
                            "description": head_unit.get("description"),
                            "generation": head_unit.get("generation"),
                            "multimedia_type": head_unit.get("multimediaType"),
                        } if head_unit else {},
                        "dcm": {
                            "supplier": dcm_info.get("supplier"),
                            "hardware_type": dcm_info.get("hardwareType"),
                            "status": dcm_info.get("dcmStatus"),
                        } if dcm_info else {},
                        "family_sharing": raw.get("familySharing"),
                        "katashiki_code": raw.get("katashikiCode"),
                        "features": active_features,
                        "capabilities_raw": active_caps,
                    }
                    break
            if not hasattr(client, "_cache"):
                client._cache = {}
            client._cache[cache_key] = vehicle_info
        except Exception:
            pass

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

    climate_settings = await safe_call(client.api.get_climate_settings(vin))
    climate_status = await safe_call(client.api.get_climate_status(vin))

    return {
        "status": status,
        "battery": battery,
        "location": location,
        "telemetry": telemetry,
        "consumption": get_consumption_estimate(),
        "capabilities": {"trips": client.api.endpoints.get("trips") is not None},
        "brand": BRAND_LABELS.get(client.auth.region.brand, "toyota"),
        "vehicle": vehicle_info,
        "climate_settings": climate_settings,
        "climate_status": climate_status,
    }


@app.get("/api/battery/{vin}")
async def api_battery(vin: str, session: str | None = Cookie(None)):
    vin = _validate_vin(vin)
    client = await _require_client(session)
    return await safe_call(client.get_electric_status(vin))


@app.get("/api/battery-history")
async def api_battery_history(session: str | None = Cookie(None), limit: int = 500):
    await _require_client(session)
    return get_snapshot_history(min(limit, 1000))


@app.get("/api/climate-settings/{vin}")
async def api_climate_settings(vin: str, session: str | None = Cookie(None)):
    vin = _validate_vin(vin)
    client = await _require_client(session)
    return await safe_call(client.api.get_climate_settings(vin))


@app.put("/api/climate-settings/{vin}")
async def api_update_climate_settings(
    vin: str, request: Request, session: str | None = Cookie(None),
):
    """Accept a climate-settings payload (same shape as GET) and PUT it back to
    the vehicle. Used by the slider/toggle UI to persist preferences."""
    vin = _validate_vin(vin)
    _require_csrf(request, session)
    client = await _require_client(session)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "expected JSON object")
    return await safe_call(client.api.update_climate_settings(vin, body))


@app.get("/api/climate-status/{vin}")
async def api_climate_status(vin: str, session: str | None = Cookie(None)):
    vin = _validate_vin(vin)
    client = await _require_client(session)
    return await safe_call(client.api.get_climate_status(vin))


@app.post("/api/climate/{vin}/{cmd}")
async def api_climate_control(
    vin: str, cmd: str, request: Request, duration: int = 10,
    session: str | None = Cookie(None),
):
    """Start or stop the remote climate control. `cmd` = start | stop."""
    vin = _validate_vin(vin)
    _require_csrf(request, session)
    if cmd not in ("start", "stop"):
        raise HTTPException(400, "invalid climate command")
    client = await _require_client(session)
    return await safe_call(client.api.send_climate_control(vin, cmd, duration))


@app.post("/api/climate-refresh/{vin}")
async def api_climate_refresh(vin: str, request: Request, session: str | None = Cookie(None)):
    vin = _validate_vin(vin)
    _require_csrf(request, session)
    client = await _require_client(session)
    return await safe_call(client.api.refresh_climate_status(vin))


@app.get("/api/telemetry/{vin}")
async def api_telemetry(vin: str, session: str | None = Cookie(None)):
    vin = _validate_vin(vin)
    client = await _require_client(session)
    return await safe_call(client.get_telemetry(vin))


@app.post("/api/refresh/{vin}")
async def api_refresh(vin: str, request: Request, session: str | None = Cookie(None)):
    vin = _validate_vin(vin)
    _require_csrf(request, session)
    client = await _require_client(session)
    # Per-VIN rate limit: 1 refresh / 60s. The car only wakes so fast.
    now = time.monotonic()
    last = _refresh_timestamps.get(vin, 0)
    if now - last < 60:
        remaining = int(60 - (now - last))
        raise HTTPException(429, f"Rate limited. Try again in {remaining}s.")
    _refresh_timestamps[vin] = now
    # Both endpoints are needed; one alone doesn't reliably wake the car.
    status_result = await safe_call(client.refresh_status(vin))
    ev_result = await safe_call(client.refresh_electric_status(vin))
    return {"status_refresh": status_result, "ev_refresh": ev_result}


@app.post("/api/command/{vin}/{command}")
async def api_command(vin: str, command: str, request: Request, session: str | None = Cookie(None)):
    """Send remote command."""
    vin = _validate_vin(vin)
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
    if session and not _command_limiter.check(session):
        raise HTTPException(status_code=429, detail="Too many attempts")
    client = await _require_client(session)
    return await safe_call(client.send_command(vin, command))


@app.post("/api/sync/{vin}")
async def api_sync(vin: str, request: Request, session: str | None = Cookie(None)):
    vin = _validate_vin(vin)
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

        trips = data.get("trips", [])
        if not trips:
            break

        new, updated = upsert_trips(trips, vin=vin)
        total_new += new
        total_updated += updated

        meta = data.get("_metadata", {}).get("pagination", {})
        next_offset = meta.get("nextOffset")
        if next_offset is None or next_offset <= offset:
            break
        offset = next_offset

    return {"new": total_new, "updated": total_updated, "db_total": get_trip_count()}


@app.get("/api/trips/{vin}")
async def api_trips(vin: str, days: int = 30, session: str | None = Cookie(None)):
    vin = _validate_vin(vin)
    client = await _require_client(session)
    return await safe_call(client.get_trips(
        vin, from_date=date.today() - timedelta(days=days), to_date=date.today(),
        route=False, summary=True, limit=50,
    ))


# --- Local DB ---

@app.get("/api/db/trips")
async def api_db_trips(limit: int = 50, offset: int = 0, from_date: str | None = None, to_date: str | None = None, vin: str | None = None, session: str | None = Cookie(None)):
    await _require_client(session)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
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
    vin = _validate_vin(vin)
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

            trips = data.get("trips", [])
            meta = data.get("_metadata", {}).get("pagination", {})
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
    # Limit request body size (10 MB max)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 10 * 1024 * 1024:
        return JSONResponse({"error": "Request body too large (max 10 MB)"}, status_code=413)
    body = await request.json()
    trips = body.get("trips", [])
    if not trips:
        return JSONResponse({"error": "No trips in data"}, status_code=400)
    if len(trips) > 10000:
        return JSONResponse({"error": "Too many trips (max 10,000)"}, status_code=400)

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
    # Cap SVG dimensions to prevent resource exhaustion
    width = max(100, min(width, 4000))
    height = max(100, min(height, 4000))
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


# --- Raw API proxy (gated behind TOYBARU_DEBUG) ---

@app.get("/api/raw/{path:path}")
async def api_raw(path: str, vin: str | None = None, session: str | None = Cookie(None)):
    if os.environ.get("TOYBARU_DEBUG", "").lower() != "true":
        raise HTTPException(status_code=403, detail="Debug endpoint disabled")
    client = await _require_client(session)
    endpoint = f"/{path}" if not path.startswith("/") else path
    return await safe_call(client.raw_request("GET", endpoint, vin=vin))


def run(host: str = "127.0.0.1", port: int = 8099):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
