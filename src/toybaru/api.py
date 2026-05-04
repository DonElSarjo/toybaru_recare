"""HTTP API layer for Toyota/Lexus/Subaru Connected Services.

Platform differences (Toyota EU, Toyota NA, Lexus EU, Lexus NA, Subaru EU,
Subaru NA) are declared in `const.RegionConfig` and snapshotted into instance
attributes in `Api.__init__`. All public methods are thin feature lookups via
`_call(feature)` — no brand/region conditionals live here.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from toybaru.auth.controller import AuthController
from toybaru.http import make_client
from toybaru.const import CLIENT_VERSION, USER_AGENT
from toybaru.exceptions import ApiError


class Api:
    """Low-level API client."""

    def __init__(self, auth: AuthController, timeout: int = 30) -> None:
        self.auth = auth
        self.timeout = timeout

        region = auth.region
        self.api_base_url = region.api_base_url
        self.api_key = region.api_key
        self.endpoints = dict(region.endpoints)
        self.endpoint_headers = dict(region.endpoint_headers)
        self._base_extra_headers = dict(region.request_headers)
        self.vin_header_keys = tuple(region.vin_headers)
        self.response_envelope = region.response_envelope or ""

        self._post_processors = {
            feat: getattr(self, f"_pp_{name}")
            for feat, name in (region.post_processors or {}).items()
        }
        self._fallbacks = {
            feat: getattr(self, f"_fb_{name}")
            for feat, name in (region.fallbacks or {}).items()
        }

    # --- HTTP plumbing ---

    def _compute_client_ref(self, uuid: str) -> str:
        """Compute x-client-ref HMAC-SHA256."""
        mac = hmac.new(CLIENT_VERSION.encode(), uuid.encode(), hashlib.sha256)
        return mac.hexdigest()

    async def _headers(self, vin: str | None = None) -> dict[str, str]:
        token = await self.auth.ensure_token()
        # Header set mirrors pytoyoda controller._generate_headers (pytoyoda
        # controller.py:410-444). The duplicates (API_KEY / x-api-key, guid /
        # x-guid) and lowercase `authorization` match the OneApp client; some
        # endpoints check one casing, some the other.
        h = {
            "authorization": f"Bearer {token}",
            "x-api-key": self.api_key,
            "API_KEY": self.api_key,
            "x-guid": self.auth.uuid,
            "guid": self.auth.uuid,
            "x-brand": self.auth.region.brand,
            "x-channel": "ONEAPP",
            "x-appversion": CLIENT_VERSION,
            "x-client-ref": self._compute_client_ref(self.auth.uuid),
            "x-correlationid": str(uuid4()),
            "user-agent": USER_AGENT,
            "Content-Type": "application/json",
            **self._base_extra_headers,
        }
        if vin:
            for key in self.vin_header_keys:
                h[key] = vin
        return h

    async def request(
        self,
        method: str,
        endpoint: str,
        vin: str | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated API request and return JSON (envelope-unwrapped)."""
        headers = await self._headers(vin)
        if extra_headers:
            headers.update(extra_headers)
        url = f"{self.api_base_url}{endpoint}"

        async with make_client(timeout=self.timeout) as client:
            resp = await client.request(method, url, headers=headers, json=body, params=params)

        if resp.status_code not in (200, 202):
            raise ApiError(resp.status_code, resp.text)

        if not resp.content:
            return {}

        data = resp.json()
        if not isinstance(data, dict):
            return data
        # "payload" is the universal wrapper used by both EU and NA backends when
        # they wrap responses. Unwrap unconditionally; platform-specific envelopes
        # (other than "payload") can still override via response_envelope.
        if "payload" in data:
            return data["payload"]
        envelope = self.response_envelope
        if envelope and envelope in data:
            return data[envelope]
        return data

    async def request_raw(
        self,
        method: str,
        endpoint: str,
        vin: str | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make an authenticated API request and return the raw response."""
        headers = await self._headers(vin)
        url = f"{self.api_base_url}{endpoint}"

        async with make_client(timeout=self.timeout) as client:
            resp = await client.request(method, url, headers=headers, json=body, params=params)

        return resp

    async def _call(
        self,
        feature: str,
        method: str = "GET",
        vin: str | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        query_suffix: str = "",
    ) -> dict[str, Any]:
        """Feature-driven API invocation.

        Resolves endpoint, headers, and post-processing from the platform
        profile. Returns `{"_unavailable": feature}` if the endpoint is not
        supported and no fallback is registered.
        """
        endpoint = self.endpoints.get(feature)
        if endpoint is None:
            fallback = self._fallbacks.get(feature)
            if fallback is not None:
                return await fallback(vin=vin)
            return {"_unavailable": feature}

        extra_headers = self.endpoint_headers.get(feature)
        url = f"{endpoint}{query_suffix}" if query_suffix else endpoint
        data = await self.request(
            method, url,
            vin=vin, body=body, params=params,
            extra_headers=extra_headers,
        )
        post = self._post_processors.get(feature)
        return post(data) if post is not None else data

    # --- High-level methods. Thin feature lookups, no conditionals. ---

    async def get_vehicles(self) -> dict[str, Any]:
        return await self._call("vehicles")

    async def get_vehicle_status(self, vin: str) -> dict[str, Any]:
        return await self._call("vehicle_status", vin=vin)

    async def get_electric_status(self, vin: str) -> dict[str, Any]:
        return await self._call("electric_status", vin=vin)

    async def refresh_electric_status(self, vin: str) -> dict[str, Any]:
        return await self._call("electric_realtime", method="POST", vin=vin)

    async def get_location(self, vin: str) -> dict[str, Any]:
        return await self._call("location", vin=vin)

    async def get_telemetry(self, vin: str) -> dict[str, Any]:
        return await self._call("telemetry", vin=vin)

    async def get_trips(
        self,
        vin: str,
        from_date: date,
        to_date: date,
        route: bool = False,
        summary: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        # Params must be in the URL path (not httpx query params) for the EU API.
        qs = (
            f"?from={from_date}&to={to_date}"
            f"&route={str(route).lower()}&summary={str(summary).lower()}"
            f"&limit={limit}&offset={offset}"
        )
        return await self._call("trips", vin=vin, query_suffix=qs)

    async def get_notifications(self, vin: str) -> dict[str, Any]:
        return await self._call("notifications", vin=vin)

    async def get_service_history(self, vin: str) -> dict[str, Any]:
        return await self._call("service_history", vin=vin)

    async def refresh_vehicle_status(self, vin: str) -> dict[str, Any]:
        return await self._call(
            "refresh_status",
            method="POST",
            vin=vin,
            body={"guid": self.auth.uuid, "vin": vin},
        )

    async def send_command(self, vin: str, command: str, extra: dict | None = None) -> dict[str, Any]:
        body = {"command": command}
        if extra:
            body.update(extra)
        return await self._call("command", method="POST", vin=vin, body=body)

    async def get_account(self) -> dict[str, Any]:
        return await self._call("account")

    async def get_climate_settings(self, vin: str) -> dict[str, Any]:
        return await self._call("climate_settings", vin=vin)

    async def update_climate_settings(self, vin: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Persist new target temperature / seat heat / defog preferences back
        to the vehicle's climate config. Same endpoint as GET, PUT method."""
        return await self._call("climate_settings", method="PUT", vin=vin, body=settings)

    async def get_climate_status(self, vin: str) -> dict[str, Any]:
        return await self._call("climate_status", vin=vin)

    async def refresh_climate_status(self, vin: str) -> dict[str, Any]:
        return await self._call("refresh_climate_status", method="POST", vin=vin)

    async def send_climate_control(self, vin: str, command: str, engine_start_time: int = 10) -> dict[str, Any]:
        """Send a climate-control command. Callers pass friendly `start`/`stop`;
        the Subaru/Toyota gateway expects `engine-start` / `engine-stop` on the
        wire (response code ONE-GLOBAL-RS-10003 confirms those are the only
        allowed values). `engine_start_time` minutes only applies to start.
        """
        wire_cmd = {"start": "engine-start", "stop": "engine-stop"}.get(command, command)
        body: dict[str, Any] = {"command": wire_cmd}
        if wire_cmd == "engine-start" and engine_start_time:
            body["remoteHvac"] = {"engineStartTime": engine_start_time}
        return await self._call("climate_control", method="POST", vin=vin, body=body)

    # --- Post-processors and fallbacks (referenced by name from RegionConfig) ---

    async def _fb_location_from_vehicle_status(self, vin: str | None = None) -> dict[str, Any]:
        """Some platforms do not expose a dedicated location endpoint; extract
        latitude/longitude from the vehicle status payload instead."""
        status = await self._call("vehicle_status", vin=vin)
        return {
            "vehicleLocation": {
                "latitude": status.get("latitude"),
                "longitude": status.get("longitude"),
            }
        }

    @staticmethod
    def _pp_normalize_na_electric(data: dict[str, Any]) -> dict[str, Any]:
        """Reshape the NA electric-status response (nested under vehicleInfo.chargeInfo)
        into the EU-style flat dict that the rest of the app expects."""
        charge_info = data.get("vehicleInfo", {}).get("chargeInfo", {})
        if not charge_info:
            charge_info = data.get("chargeInfo", data)

        plug = charge_info.get("plugStatus")
        connector = charge_info.get("connectorStatus")
        remaining = charge_info.get("remainingChargeTime")
        if plug == 4 or plug == 40:
            charging_status = "charging"
        elif plug == 12 or (plug is not None and connector in (None, 0)):
            charging_status = "not connected"
        elif connector and connector > 0:
            charging_status = "connected"
        else:
            charging_status = str(plug) if plug is not None else "unknown"

        result: dict[str, Any] = {
            "batteryLevel": charge_info.get("chargeRemainingAmount"),
            "evRange": {
                "value": charge_info.get("evDistance"),
                "unit": charge_info.get("evDistanceUnit", "km"),
            },
            "evRangeWithAc": {
                "value": charge_info.get("evDistanceAC"),
                "unit": charge_info.get("evDistanceUnit", "km"),
            },
            "chargingStatus": charging_status,
            "plugStatus": plug,
            "chargeType": charge_info.get("chargeType"),
            "connectorStatus": connector,
            "plugInHistory": charge_info.get("plugInHistory"),
        }

        if remaining is not None and remaining != 65535:
            result["remainingChargeTime"] = remaining

        acq = data.get("vehicleInfo", {}).get("acquisitionDatetime")
        if acq:
            result["lastUpdateTimestamp"] = acq

        solar = data.get("vehicleInfo", {}).get("solarPowerGenerationInfo", {})
        if solar:
            avail = solar.get("solarInfoAvailable", -1)
            result["solar"] = {
                "equipped": avail >= 0,
                "cumulativeDistance": solar.get("solarCumulativeEvTravelableDistance"),
                "cumulativePower": solar.get("solarCumulativePowerGeneration"),
            }

        hvac = data.get("vehicleInfo", {}).get("remoteHvacInfo", {})
        if hvac:
            result["hvac"] = {
                "settingTemperature": hvac.get("settingTemperature"),
                "temperatureLevel": hvac.get("temperaturelevel"),
                "blowerOn": hvac.get("blowerStatus", 0) != 0,
                "frontDefogger": hvac.get("frontDefoggerStatus", 0) != 0,
                "rearDefogger": hvac.get("rearDefoggerStatus", 0) != 0,
                "hvacMode": hvac.get("remoteHvacMode", 0),
                "hvacProhibited": hvac.get("remoteHvacProhibitionSignal", 0) == 1,
            }

        return result
