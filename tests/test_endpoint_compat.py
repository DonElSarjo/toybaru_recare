"""Phase 4 provider endpoint-version and fallback tests (no network)."""

from unittest.mock import AsyncMock

import pytest

from toybaru.api import Api
from toybaru.const import REGIONS
from toybaru.exceptions import ApiError


class _FakeAuth:
    def __init__(self, region):
        self.region = region
        self.uuid = "guid-1234"

    async def ensure_token(self):
        return "token"


def _api(region: str) -> Api:
    return Api(_FakeAuth(REGIONS[region]))


def test_toyota_eu_uses_migrated_2026_routes_and_read_fallbacks():
    region = REGIONS["toyota-eu"]
    assert region.endpoints["vehicle_status"] == "/v1/vehicle/status"
    assert region.endpoints["refresh_status"] == "/v1/remote/status"
    assert region.endpoints["climate_settings"] == "/v1/vehicle/climate-settings"
    assert region.endpoints["climate_status"] == "/v1/vehicle/climate-status"
    assert region.endpoints["climate_control"] == "/v2/remote/climate-control"
    assert region.endpoints["refresh_climate_status"] == "/v1/remote/refresh-climate-status"
    assert region.endpoint_fallbacks["vehicle_status"] == (
        "/v1/global/remote/status",
    )
    assert region.request_styles["climate_control"] == "v2"


def test_other_provider_profiles_do_not_inherit_toyota_route_migration():
    for profile in ("lexus-eu", "subaru-eu", "subaru-na"):
        region = REGIONS[profile]
        assert region.endpoints["vehicle_status"] == "/v1/global/remote/status"
        assert region.endpoints["refresh_status"] == "/v1/global/remote/refresh-status"
        assert region.endpoints["climate_control"] == "/v1/global/remote/climate-control"
        assert not region.endpoint_fallbacks
        assert not region.request_styles


async def test_safe_get_falls_back_on_endpoint_compatibility_failure():
    api = _api("toyota-eu")
    api.request = AsyncMock(side_effect=[ApiError(404, "missing"), {"ok": True}])

    result = await api.get_vehicle_status("JVIN0000000000000")

    assert result == {"ok": True}
    assert [call.args[1] for call in api.request.await_args_list] == [
        "/v1/vehicle/status",
        "/v1/global/remote/status",
    ]


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_read_fallback_does_not_mask_auth_rate_or_server_failures(status):
    api = _api("toyota-eu")
    api.request = AsyncMock(side_effect=ApiError(status, "failure"))

    with pytest.raises(ApiError):
        await api.get_vehicle_status("JVIN0000000000000")

    assert api.request.await_count == 1


async def test_write_request_never_uses_configured_fallback():
    api = _api("toyota-eu")
    api.endpoint_fallbacks["refresh_status"] = ("/legacy/wake",)
    api.request = AsyncMock(side_effect=ApiError(404, "missing"))

    with pytest.raises(ApiError):
        await api.refresh_vehicle_status("JVIN0000000000000")

    api.request.assert_awaited_once()


async def test_refresh_status_body_is_selected_by_provider_profile():
    toyota = _api("toyota-eu")
    toyota._call = AsyncMock(return_value={})
    await toyota.refresh_vehicle_status("JVIN0000000000000")
    toyota._call.assert_awaited_once_with(
        "refresh_status", method="POST", vin="JVIN0000000000000", body=None
    )

    subaru = _api("subaru-na")
    subaru._call = AsyncMock(return_value={})
    await subaru.refresh_vehicle_status("JVIN0000000000000")
    subaru._call.assert_awaited_once_with(
        "refresh_status",
        method="POST",
        vin="JVIN0000000000000",
        body={"guid": "guid-1234", "vin": "JVIN0000000000000"},
    )


async def test_climate_control_body_is_selected_by_provider_profile():
    toyota = _api("toyota-eu")
    toyota._call = AsyncMock(return_value={})
    await toyota.send_climate_control(
        "JVIN0000000000000",
        "start",
        15,
        settings={"temperature": 21.5, "temperatureUnit": "C"},
    )
    toyota._call.assert_awaited_once_with(
        "climate_control",
        method="POST",
        vin="JVIN0000000000000",
        body={
            "command": "start",
            "duration": 15,
            "temperature": {"value": 21.5, "unit": "C"},
            "saveSettings": False,
        },
    )

    subaru = _api("subaru-na")
    subaru._call = AsyncMock(return_value={})
    await subaru.send_climate_control("JVIN0000000000000", "start", 15)
    subaru._call.assert_awaited_once_with(
        "climate_control",
        method="POST",
        vin="JVIN0000000000000",
        body={"command": "engine-start", "remoteHvac": {"engineStartTime": 15}},
    )


async def test_toyota_eu_settings_write_is_not_mapped_to_a_vehicle_command():
    api = _api("toyota-eu")
    api._call = AsyncMock()

    result = await api.update_climate_settings("JVIN0000000000000", {"temperature": 20})

    assert result["_unavailable"] == "climate_settings_write"
    api._call.assert_not_awaited()
