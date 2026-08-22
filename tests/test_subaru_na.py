"""Phase F — verify the confirmed Subaru NA recipe is what the app produces.

These are construction tests (no network): they assert that Api(subaru-na) builds
exactly the header recipe + URLs we proved work live (na_discovery/FINDINGS.md,
docs/api-inventory.md), and that the EU recipe is unchanged.
"""

from unittest.mock import AsyncMock

from toybaru.api import Api
from toybaru.const import REGIONS


class _FakeAuth:
    """Minimal stand-in for AuthController for header/URL construction."""

    def __init__(self, region):
        self.region = region
        self.uuid = "guid-1234"

    async def ensure_token(self):
        return "tok-abc"


def _api(region_key):
    return Api(_FakeAuth(REGIONS[region_key]))


# --- region config ---

def test_subaru_na_config():
    r = REGIONS["subaru-na"]
    assert r.api_base_url == "https://onecdn.telematicsct.com/oneapi"
    assert r.client_id == "oneappsdkclient"
    assert r.oauth_uses_basic_auth is False
    assert r.vin_headers == ("VIN", "vin", "X-VIN")
    # core under /oneapi (relative), charging absolute under /charging
    assert r.endpoints["electric_status"] == "/v2/electric/status"
    assert r.endpoints["vehicle_health"] == "/v1/vehiclehealth/status"
    assert r.endpoints["charge_history"].startswith("https://onecdn.telematicsct.com/charging/")
    assert r.endpoints["charge_statistics"].startswith("https://onecdn.telematicsct.com/charging/")
    # trips / standalone telemetry are not available for Subaru NA
    assert r.endpoints["trips"] is None
    assert r.endpoints["telemetry"] is None


def test_na_regions_skip_basic_auth():
    # public-client realms (oneappsdkclient) must not send Basic on token/refresh
    assert REGIONS["subaru-na"].oauth_uses_basic_auth is False
    assert REGIONS["toyota-na"].oauth_uses_basic_auth is False
    assert REGIONS["lexus-na"].oauth_uses_basic_auth is False
    # EU client_id matches the Basic-auth client -> keep Basic
    assert REGIONS["subaru-eu"].oauth_uses_basic_auth is True
    assert REGIONS["toyota-eu"].oauth_uses_basic_auth is True


# --- header recipe ---

async def test_subaru_na_headers_match_confirmed_recipe():
    h = await _api("subaru-na")._headers("JVIN0000000000000")

    # present + correct values
    assert h["authorization"] == "Bearer tok-abc"
    assert h["x-api-key"] == REGIONS["subaru-na"].api_key
    assert h["x-guid"] == "guid-1234"
    assert h["x-channel"] == "oneapp"          # overridden from base ONEAPP
    assert h["x-appversion"] == "2.3.1"
    assert "com.subaru.oneapp" in h["user-agent"]
    assert h["x-appbrand"] == "S"
    assert h["x-osversion"] == "Android"
    assert h["x-osname"] == "android"
    assert h["x-device-timezone"] == "UTC"
    assert h["X-LOCALE"] == "en-US"

    # VIN in all three header keys (X-VIN for /charging, VIN+vin for /oneapi)
    assert h["VIN"] == h["vin"] == h["X-VIN"] == "JVIN0000000000000"

    # dropped: the Toyota-only headers the proven recipe must NOT send
    for absent in ("x-client-ref", "x-correlationid", "x-brand", "API_KEY", "guid"):
        assert absent not in h, f"{absent} should be dropped for Subaru NA"


async def test_subaru_eu_headers_unchanged():
    h = await _api("subaru-eu")._headers("VIN")
    # EU still sends the Toyota-style recipe
    assert h["x-channel"] == "ONEAPP"
    assert "x-client-ref" in h
    assert "x-correlationid" in h
    assert h["x-brand"] == "S"


# --- URL resolution ---

def test_url_relative_vs_absolute():
    api = _api("subaru-na")
    assert api._url("/v2/electric/status") == "https://onecdn.telematicsct.com/oneapi/v2/electric/status"
    absolute = "https://onecdn.telematicsct.com/charging/v2/vehicle/charge-history"
    assert api._url(absolute) == absolute


# --- charge-history post-processor ---

def test_pp_na_charge_history_flattens_per_vin_wrapper():
    data = [{"vin": "x", "charging_sessions": [{"id": 1}, {"id": 2}]}]
    assert Api._pp_na_charge_history(data) == {"sessions": [{"id": 1}, {"id": 2}]}


def test_pp_na_charge_history_empty():
    assert Api._pp_na_charge_history([]) == {"sessions": []}
    assert Api._pp_na_charge_history([{"vin": "x", "charging_sessions": []}]) == {"sessions": []}


def test_pp_na_electric_preserves_read_only_charge_management_fields():
    data = {
        "vehicleInfo": {
            "chargeInfo": {
                "chargeRemainingAmount": 72,
                "remainingChargingTime": 95,
                "canSetNextChargingEvent": True,
                "chargingSchedules": [
                    {"enabled": True, "daysOfWeek": ["MON"], "startTime": "23:00"}
                ],
                "nextChargingEvent": {"startTime": "23:00"},
            }
        }
    }

    result = Api._pp_normalize_na_electric(data)

    assert result["remainingChargeTime"] == 95
    assert result["canSetNextChargingEvent"] is True
    assert result["chargingSchedules"] == data["vehicleInfo"]["chargeInfo"]["chargingSchedules"]
    assert result["nextChargingEvent"] == {"startTime": "23:00"}


def test_pp_na_electric_ignores_remaining_time_sentinel():
    result = Api._pp_normalize_na_electric({"chargeInfo": {"remainingChargeTime": 65535}})
    assert "remainingChargeTime" not in result


async def test_electric_command_transport_uses_profile_endpoint_and_envelope():
    api = _api("subaru-na")
    api._call = AsyncMock(return_value={"returnCode": "000000"})
    reservation = {
        "chargeType": "startOnly",
        "day": "MONDAY",
        "startTime": {"hour": 23, "minute": 0},
    }

    result = await api.send_electric_command(
        "JVIN0000000000000", "SET_CHARGING_TIME", reservation
    )

    assert result == {"returnCode": "000000"}
    api._call.assert_awaited_once_with(
        "electric_command",
        method="POST",
        vin="JVIN0000000000000",
        body={"command": "SET_CHARGING_TIME", "reservationCharge": reservation},
    )


# --- web routes registered + auth-guarded ---

_VIN = "JF2ABCDE6GH123456"  # synthetic, valid VIN format


def test_new_routes_registered_and_require_auth():
    from fastapi.testclient import TestClient
    from toybaru.web import app

    client = TestClient(app)
    for path in (
        f"/api/vehicle-health/{_VIN}",
        f"/api/charge-history/{_VIN}",
        f"/api/charge-statistics/{_VIN}",
        f"/api/notifications/{_VIN}",
        f"/api/service-history/{_VIN}",
        f"/api/db/charges?vin={_VIN}",
    ):
        resp = client.get(path)
        # registered (not 404) and guarded (401 without a session)
        assert resp.status_code == 401, f"{path} -> {resp.status_code}"
