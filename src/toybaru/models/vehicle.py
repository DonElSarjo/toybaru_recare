"""Vehicle and status models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Vehicle(BaseModel):
    """Vehicle info from the vehicle list endpoint."""

    vin: str | None = None
    alias: str | None = Field(None, alias="nickName")
    model_description: str | None = Field(None, alias="displayModelDescription")
    model_name: str | None = Field(None, alias="modelName")
    model_year: str | None = Field(None, alias="modelYear")
    image: str | None = None
    color: str | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class VehicleStatus(BaseModel):
    """Vehicle status (doors, windows, odometer)."""

    occurrence_date: datetime | None = Field(None, alias="occurrenceDate")
    model_config = {"extra": "allow", "populate_by_name": True}


class ElectricStatus(BaseModel):
    """EV-specific status (battery, charging, range)."""

    battery_level: int | None = Field(None, alias="batteryLevel")
    charging_status: str | None = Field(None, alias="chargingStatus")
    ev_range: dict | None = Field(None, alias="evRange")
    ev_range_with_ac: dict | None = Field(None, alias="evRangeWithAc")
    remaining_charge_time: int | None = Field(None, alias="remainingChargeTime")
    can_set_next_charging_event: bool | None = Field(
        None, alias="canSetNextChargingEvent"
    )
    charging_schedules: list[dict[str, Any]] | None = Field(
        None, alias="chargingSchedules"
    )
    next_charging_event: dict[str, Any] | None = Field(
        None, alias="nextChargingEvent"
    )
    last_update_timestamp: datetime | None = Field(None, alias="lastUpdateTimestamp")
    model_config = {"extra": "allow", "populate_by_name": True}


class ChargeInfo(BaseModel):
    """Charge info from NA-style electric status response."""

    charge_remaining_amount: int | None = Field(None, alias="chargeRemainingAmount")
    ev_distance: float | None = Field(None, alias="evDistance")
    ev_distance_ac: float | None = Field(None, alias="evDistanceAC")
    ev_distance_unit: str | None = Field(None, alias="evDistanceUnit")
    charge_type: int | None = Field(None, alias="chargeType")
    connector_status: int | None = Field(None, alias="connectorStatus")
    charge_status: str | None = Field(None, alias="chargeStatus")
    model_config = {"extra": "allow", "populate_by_name": True}


class Location(BaseModel):
    """Vehicle location."""

    latitude: float | None = None
    longitude: float | None = None
    display_name: str | None = Field(None, alias="displayName")
    location_acquisition_datetime: datetime | None = Field(
        None, alias="locationAcquisitionDatetime"
    )
    model_config = {"extra": "allow", "populate_by_name": True}


class TripSummary(BaseModel):
    """Summary of a single trip."""

    length: int | None = None  # meters
    duration: int | None = None  # seconds
    max_speed: float | None = Field(None, alias="maxSpeed")
    average_speed: float | None = Field(None, alias="averageSpeed")
    fuel_consumption: float | None = Field(None, alias="fuelConsumption")  # ml
    start_lat: float | None = Field(None, alias="startLat")
    start_lon: float | None = Field(None, alias="startLon")
    start_ts: datetime | None = Field(None, alias="startTs")
    end_lat: float | None = Field(None, alias="endLat")
    end_lon: float | None = Field(None, alias="endLon")
    end_ts: datetime | None = Field(None, alias="endTs")
    model_config = {"extra": "allow", "populate_by_name": True}


class TripScores(BaseModel):
    """Driving scores for a trip."""

    global_score: int | None = Field(None, alias="global")
    acceleration: int | None = None
    braking: int | None = None
    constant_speed: int | None = Field(None, alias="constantSpeed")
    model_config = {"extra": "allow", "populate_by_name": True}


class TripHDC(BaseModel):
    """EV/hybrid driving composition for a trip."""

    ev_time: int | None = Field(None, alias="evTime")
    ev_distance: int | None = Field(None, alias="evDistance")
    charge_time: int | None = Field(None, alias="chargeTime")
    charge_dist: int | None = Field(None, alias="chargeDist")
    model_config = {"extra": "allow", "populate_by_name": True}


class RoutePoint(BaseModel):
    """Single point on a trip route."""

    lat: float | None = None
    lon: float | None = None
    overspeed: bool | None = None
    highway: bool | None = None
    is_ev: bool | None = Field(None, alias="isEv")
    model_config = {"extra": "allow", "populate_by_name": True}


class Trip(BaseModel):
    """A single trip."""

    id: str | None = None
    category: int | None = None
    summary: TripSummary | None = None
    scores: TripScores | None = None
    hdc: TripHDC | None = None
    route: list[RoutePoint] | None = None
    model_config = {"extra": "allow", "populate_by_name": True}


class Telemetry(BaseModel):
    """Telemetry data (odometer, fuel, etc.)."""

    odometer: dict | None = None
    fuel_type: str | None = Field(None, alias="fuelType")
    model_config = {"extra": "allow", "populate_by_name": True}
