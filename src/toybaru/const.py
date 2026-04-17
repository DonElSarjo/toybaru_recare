"""API constants and regional configurations."""

import json
import os
from dataclasses import dataclass, fields
from pathlib import Path

# Data directory - configurable via env var for Docker
DATA_DIR = Path(os.environ.get("TOYBARU_DATA_DIR", Path.home() / ".config" / "toybaru"))


@dataclass(frozen=True)
class RegionConfig:
    name: str
    auth_realm: str
    api_base_url: str
    client_id: str
    redirect_uri: str
    basic_auth: str  # Base64 encoded client_id:client_secret
    api_key: str
    brand: str
    region: str
    auth_service: str = ""

# Brand -> Region mapping for the login UI
BRANDS = {
    "subaru": {
        "label": "Subaru",
        "regions": ["subaru-eu", "subaru-na"],
    },
    "toyota": {
        "label": "Toyota",
        "regions": ["toyota-eu", "toyota-na"],
    },
    "toyota-na": {
        "label": "Toyota NA",
        "regions": ["toyota-na"],
    },
}

# Built-in defaults
_DEFAULTS = {
    "subaru-eu": RegionConfig(
        name="Subaru EU",
        auth_realm="https://b2c-login.toyota-europe.com/oauth2/realms/root/realms/alliance-subaru",
        api_base_url="https://ctpa-oneapi.tceu-ctp-prd.toyotaconnectedeurope.io",
        client_id="8c4921b0b08901fef389ce1af49c4e10.subaru.com",
        redirect_uri="com.subaru.oneapp:/oauth2Callback",
        basic_auth="OGM0OTIxYjBiMDg5MDFmZWYzODljZTFhZjQ5YzRlMTAuc3ViYXJ1LmNvbTpJaGNkcjV4YmhIYlRSMk9aOGdRa3YyNTZicmhTYjc=",
        api_key="tTZipv6liF74PwMfk9Ed68AQ0bISswwf3iHQdqcF",
        brand="S",
        region="EU",
        auth_service="oneapp",
    ),
    "subaru-na": RegionConfig(
        name="Subaru NA",
        auth_realm="https://login.subarudriverslogin.com/oauth2/realms/root/realms/tmna-native",
        api_base_url="https://api.telematicsct.com",
        client_id="oneappsdkclient",
        redirect_uri="com.toyota.oneapp:/oauth2Callback",
        basic_auth="b25lYXBwOm9uZWFwcA==",
        api_key="pypIHG015k4ABHWbcI4G0a94F7cC0JDo1OynpAsG", # thx to SwordfishLocal2677
        brand="S",
        region="NA",
        auth_service="",
    ),
    "toyota-na": RegionConfig(
        name="Toyota NA",
        auth_realm="https://login.toyotadriverslogin.com/oauth2/realms/root/realms/tmna-native", # thx to antifort
        api_base_url="https://api.telematicsct.com",
        client_id="oneappsdkclient",
        redirect_uri="com.toyota.oneapp:/oauth2Callback",
        basic_auth="b25lYXBwOm9uZWFwcA==",
        api_key="Y1aVonEtOa18cDwNLGTjt1zqD7aLahwc30WvvvQE", # thx to antifort
        brand="T",
        region="NA",
        auth_service="",
    ),
    "toyota-eu": RegionConfig(
        name="Toyota EU",
        auth_realm="https://b2c-login.toyota-europe.com/oauth2/realms/root/realms/tme",
        api_base_url="https://ctpa-oneapi.tceu-ctp-prd.toyotaconnectedeurope.io",
        client_id="oneapp",
        redirect_uri="com.toyota.oneapp:/oauth2Callback",
        basic_auth="b25lYXBwOm9uZWFwcA==",
        api_key="tTZipv6liF74PwMfk9Ed68AQ0bISswwf3iHQdqcF",
        brand="T",
        region="EU",
        auth_service="oneapp",
    ),
    "toyota-na": RegionConfig(
        name="Toyota NA",
        auth_realm="https://login.toyotadriverslogin.com/oauth2/realms/root/realms/tmna-native",
        api_base_url="https://onecdn.telematicsct.com/oneapi",
        client_id="oneappsdkclient",
        redirect_uri="com.toyota.oneapp:/oauth2Callback",
        basic_auth="",
        api_key="Y1aVonEtOa18cDwNLGTjt1zqD7aLahwc30WvvvQE",
        brand="T",
        region="US",
        auth_service="OneAppSignIn",
    ),
}


def _load_regions() -> dict[str, RegionConfig]:
    """Load region configs: built-in defaults, overridden by regions.json if present."""
    regions = dict(_DEFAULTS)

    # Alias map so lowercase keys from user config resolve correctly
    _alias = {"eu": "subaru-eu", "na": "subaru-na"}

    # Check for user config file
    config_path = DATA_DIR / "regions.json"
    if config_path.exists():
        try:
            user_config = json.loads(config_path.read_text())
            for region_name, overrides in user_config.items():
                # Resolve aliases for legacy lowercase keys
                resolved = _alias.get(region_name.lower(), region_name)
                if resolved in regions:
                    # Merge: start with defaults, override with user values
                    base = {f.name: getattr(regions[resolved], f.name) for f in fields(RegionConfig)}
                    base.update(overrides)
                    regions[resolved] = RegionConfig(**base)
                else:
                    # New region entirely — preserve original casing
                    regions[region_name] = RegionConfig(**overrides)
        except Exception as e:
            print(f"Warning: Could not load {config_path}: {e}")

    # Backward compat aliases for old region keys
    if "subaru-eu" in regions and "EU" not in regions:
        regions["EU"] = regions["subaru-eu"]
    if "subaru-na" in regions and "NA" not in regions:
        regions["NA"] = regions["subaru-na"]

    return regions


REGIONS = _load_regions()

# Shared constants
CLIENT_VERSION = "2.19.0"
USER_AGENT = "okhttp/4.10.0"

# Endpoint paths (EU-style, most complete)
VEHICLES_ENDPOINT = "/v2/vehicle/guid"
VEHICLE_LOCATION_ENDPOINT = "/v1/location"
VEHICLE_STATUS_ENDPOINT = "/v1/global/remote/status"
VEHICLE_ENGINE_STATUS_ENDPOINT = "/v1/global/remote/engine-status"
VEHICLE_REFRESH_STATUS_ENDPOINT = "/v1/global/remote/refresh-status"
VEHICLE_ELECTRIC_STATUS_ENDPOINT = "/v1/vehicle/electric/status"
VEHICLE_ELECTRIC_REALTIME_ENDPOINT = "/v1/global/remote/electric/realtime-status"
VEHICLE_ELECTRIC_COMMAND_ENDPOINT = "/v1/global/remote/electric/command"
VEHICLE_TELEMETRY_ENDPOINT = "/v3/telemetry"
VEHICLE_TRIPS_ENDPOINT = "/v1/trips"
VEHICLE_NOTIFICATIONS_ENDPOINT = "/v2/notification/history"
VEHICLE_SERVICE_HISTORY_ENDPOINT = "/v1/servicehistory/vehicle/summary"
VEHICLE_COMMAND_ENDPOINT = "/v1/global/remote/command"
VEHICLE_ACCOUNT_ENDPOINT = "/v4/account"
