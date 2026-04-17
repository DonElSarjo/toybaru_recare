"""High-level client that combines auth + API into a convenient interface."""

from __future__ import annotations

from datetime import date
from typing import Any

from toybaru.api import Api
from toybaru.auth.controller import AuthController
from toybaru.const import REGIONS, RegionConfig
from toybaru.models.vehicle import (
    ChargeInfo,
    ElectricStatus,
    Location,
    Telemetry,
    Trip,
    Vehicle,
    VehicleStatus,
)


class ToybaruClient:
    """Main client for interacting with the Solterra Connected Services."""

    def __init__(
        self,
        username: str,
        password: str,
        region: str = "subaru-eu",
    ) -> None:
        region_config = REGIONS.get(region)
        if not region_config:
            raise ValueError(f"Unknown region: {region}. Available: {', '.join(REGIONS)}")

        self.auth = AuthController(region_config, username, password)
        self.api = Api(self.auth)

    async def login(self) -> str:
        """Authenticate and return the user UUID."""
        await self.auth.ensure_token()
        return self.auth.uuid

    async def submit_otp(self, code: str) -> str:
        """Submit OTP code and complete authentication. Returns UUID."""
        await self.auth.submit_otp(code)
        return self.auth.uuid

    async def get_vehicles(self) -> list[Vehicle]:
        """Get list of vehicles linked to the account."""
        data = await self.api.get_vehicles()
        # EU returns list directly or in "payload"
        vehicles_data = data if isinstance(data, list) else data.get("payload", data)
        if isinstance(vehicles_data, list):
            return [Vehicle.model_validate(v) for v in vehicles_data]
        return []

    async def get_vehicle_status(self, vin: str) -> dict[str, Any]:
        """Get full vehicle status (doors, windows, etc.). Returns raw dict."""
        return await self.api.get_vehicle_status(vin)

    async def get_electric_status(self, vin: str) -> dict[str, Any]:
        """Get EV battery/charging status. Returns raw dict for maximum data visibility."""
        return await self.api.get_electric_status(vin)

    async def get_location(self, vin: str) -> dict[str, Any]:
        """Get last known vehicle location."""
        return await self.api.get_location(vin)

    async def get_telemetry(self, vin: str) -> dict[str, Any]:
        """Get telemetry (odometer, fuel/energy data)."""
        return await self.api.get_telemetry(vin)

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
        """Get trip history."""
        return await self.api.get_trips(vin, from_date, to_date, route, summary, limit, offset)

    async def get_notifications(self, vin: str) -> dict[str, Any]:
        """Get notification history."""
        return await self.api.get_notifications(vin)

    async def get_service_history(self, vin: str) -> dict[str, Any]:
        """Get service history."""
        return await self.api.get_service_history(vin)

    async def refresh_status(self, vin: str) -> dict[str, Any]:
        """Request fresh status from vehicle."""
        return await self.api.refresh_vehicle_status(vin)

    async def refresh_electric_status(self, vin: str) -> dict[str, Any]:
        """Request fresh EV status from vehicle."""
        return await self.api.refresh_electric_status(vin)

    async def send_command(self, vin: str, command: str, extra: dict | None = None) -> dict[str, Any]:
        """Send remote command (door-lock, door-unlock, engine-start, engine-stop)."""
        return await self.api.send_command(vin, command, extra)

    async def get_account(self) -> dict[str, Any]:
        """Get account info."""
        return await self.api.get_account()

    async def raw_request(
        self, method: str, endpoint: str, vin: str | None = None
    ) -> dict[str, Any]:
        """Make a raw API request to any endpoint. For exploration."""
        return await self.api.request(method, endpoint, vin=vin)

    async def raw_request_full(
        self, method: str, endpoint: str, vin: str | None = None
    ):
        """Make a raw API request and return the full httpx.Response."""
        return await self.api.request_raw(method, endpoint, vin=vin)
