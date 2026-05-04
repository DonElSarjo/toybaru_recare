"""API constants and regional configurations."""

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

DATA_DIR = Path(os.environ.get("TOYBARU_DATA_DIR", Path.home() / ".config" / "toybaru"))


@dataclass(frozen=True)
class RegionConfig:
    """Platform profile. All per-(brand × region) differences live here.

    The `endpoints`, `endpoint_headers`, `request_headers`, `vin_headers`,
    `response_envelope`, and `auth_headers` fields are read by Api/AuthController
    at construction time — downstream code never branches on brand or region.
    """
    name: str
    auth_realm: str
    api_base_url: str
    client_id: str
    redirect_uri: str
    basic_auth: str
    api_key: str
    brand: str              # "T" | "L" | "S"
    region: str             # "EU" | "NA" | "US"
    auth_service: str = ""
    endpoints: dict = field(default_factory=dict)           # feature -> URL or None
    endpoint_headers: dict = field(default_factory=dict)    # feature -> extra headers
    request_headers: dict = field(default_factory=dict)     # applied to every API request
    vin_headers: tuple = ("VIN",)                           # keys under which VIN is set
    response_envelope: str = ""                             # e.g. "payload" for NA unwrap
    auth_headers: dict = field(default_factory=dict)        # extra headers for OAuth flow
    post_processors: dict = field(default_factory=dict)     # feature -> Api._pp_<name>
    fallbacks: dict = field(default_factory=dict)           # feature -> Api._fb_<name> (used when endpoint is None)


# Shared HTTP constants
CLIENT_VERSION = "2.19.0"
USER_AGENT = "okhttp/4.10.0"

# --- Endpoint libraries. Feature keys are stable; platform builders pick per feature. ---

_ENDPOINTS_EU = {
    "vehicles": "/v2/vehicle/guid",
    "vehicle_status": "/v1/global/remote/status",
    "engine_status": "/v1/global/remote/engine-status",
    "refresh_status": "/v1/global/remote/refresh-status",
    "electric_status": "/v1/vehicle/electric/status",
    "electric_realtime": "/v1/global/remote/electric/realtime-status",
    "electric_command": "/v1/global/remote/electric/command",
    "location": "/v1/location",
    "telemetry": "/v3/telemetry",
    "trips": "/v1/trips",
    "command": "/v1/global/remote/command",
    "notifications": "/v2/notification/history",
    "service_history": "/v1/servicehistory/vehicle/summary",
    "climate_settings": "/v1/global/remote/climate-settings",
    "climate_status": "/v1/global/remote/climate-status",
    "climate_control": "/v1/global/remote/climate-control",
    "refresh_climate_status": "/v1/global/remote/refresh-climate-status",
    "account": "/v4/account",
}

_ENDPOINTS_NA = {
    "vehicles": "/v2/vehicle/guid",
    "vehicle_status": "/v1/global/remote/status",
    "engine_status": "/v1/global/remote/engine-status",
    "refresh_status": "/v1/global/remote/refresh-status",
    "electric_status": "/v2/electric/status",
    "electric_realtime": "/v1/global/remote/electric/realtime-status",
    "electric_command": "/v1/global/remote/electric/command",
    "location": None,           # NA derives location from vehicle_status payload
    "telemetry": "/v2/telemetry",
    "trips": None,              # Not available on NA
    "command": "/v1/global/remote/command",
    "notifications": "/v2/notification/history",
    "service_history": "/v1/servicehistory/vehicle/summary",
    "climate_settings": "/v1/global/remote/climate-settings",
    "climate_status": "/v1/global/remote/climate-status",
    "climate_control": "/v1/global/remote/climate-control",
    "refresh_climate_status": "/v1/global/remote/refresh-climate-status",
    "account": "/v4/account",
}

# Brand code -> short key for template/i18n lookups
BRAND_LABELS = {"T": "toyota", "L": "lexus", "S": "subaru"}

# Login-UI brand -> region options
BRANDS = {
    "toyota": {"label": "Toyota", "regions": ["toyota-eu", "toyota-na"]},
    "lexus":  {"label": "Lexus",  "regions": ["lexus-eu", "lexus-na"]},
    "subaru": {"label": "Subaru", "regions": ["subaru-eu", "subaru-na"]},
}


# --- Platform builders. All brand/region differences are declared here, once. ---

def _toyota_eu() -> RegionConfig:
    return RegionConfig(
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
        endpoints=dict(_ENDPOINTS_EU),
        endpoint_headers={},
        request_headers={"x-region": "EU"},
        vin_headers=("VIN",),
        response_envelope="",
        auth_headers={},
    )


def _toyota_na() -> RegionConfig:
    return RegionConfig(
        name="Toyota NA",
        auth_realm="https://login.toyotadriverslogin.com/oauth2/realms/root/realms/tmna-native",
        api_base_url="https://onecdn.telematicsct.com/oneapi",
        client_id="oneappsdkclient",
        redirect_uri="com.toyota.oneapp:/oauth2Callback",
        basic_auth="b25lYXBwOm9uZWFwcA==",
        api_key="Y1aVonEtOa18cDwNLGTjt1zqD7aLahwc30WvvvQE",
        brand="T",
        region="US",
        auth_service="OneAppSignIn",
        endpoints=dict(_ENDPOINTS_NA),
        endpoint_headers={"telemetry": {"GENERATION": "17CYPLUS"}},
        request_headers={"x-region": "US", "X-LOCALE": "en-US"},
        vin_headers=("VIN", "vin"),
        response_envelope="payload",
        auth_headers={},
        post_processors={"electric_status": "normalize_na_electric"},
        fallbacks={"location": "location_from_vehicle_status"},
    )


def _lexus_eu() -> RegionConfig:
    # Lexus EU shares Toyota EU OAuth realm + credentials (pytoyoda controller.py:92-99).
    # Only additional brand-identification headers differ.
    base = _toyota_eu()
    return RegionConfig(
        name="Lexus EU",
        auth_realm=base.auth_realm,
        api_base_url=base.api_base_url,
        client_id=base.client_id,
        redirect_uri=base.redirect_uri,
        basic_auth=base.basic_auth,
        api_key=base.api_key,
        brand="L",
        region="EU",
        auth_service=base.auth_service,
        endpoints=dict(base.endpoints),
        endpoint_headers=dict(base.endpoint_headers),
        request_headers={**base.request_headers, "x-appbrand": "L", "brand": "L"},
        vin_headers=base.vin_headers,
        response_envelope=base.response_envelope,
        auth_headers={**base.auth_headers, "x-appbrand": "L", "brand": "L"},
        post_processors=dict(base.post_processors),
        fallbacks=dict(base.fallbacks),
    )


def _lexus_na() -> RegionConfig:
    # Lexus NA creds are not publicly documented. We start with Toyota NA creds and
    # Lexus brand headers — users can override via regions.json if real-world auth differs.
    base = _toyota_na()
    return RegionConfig(
        name="Lexus NA",
        auth_realm=base.auth_realm,
        api_base_url=base.api_base_url,
        client_id=base.client_id,
        redirect_uri=base.redirect_uri,
        basic_auth=base.basic_auth,
        api_key=base.api_key,
        brand="L",
        region="US",
        auth_service=base.auth_service,
        endpoints=dict(base.endpoints),
        endpoint_headers=dict(base.endpoint_headers),
        request_headers={**base.request_headers, "x-appbrand": "L", "brand": "L"},
        vin_headers=base.vin_headers,
        response_envelope=base.response_envelope,
        auth_headers={**base.auth_headers, "x-appbrand": "L", "brand": "L"},
        post_processors=dict(base.post_processors),
        fallbacks=dict(base.fallbacks),
    )


def _subaru_eu() -> RegionConfig:
    # pytoyoda/controller.py:432-434 — Subaru needs `brand` + `x-appbrand` in
    # addition to the standard `x-brand` so the gateway routes it through the
    # alliance-subaru pipeline rather than the Toyota TME pipeline.
    return RegionConfig(
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
        endpoints=dict(_ENDPOINTS_EU),
        endpoint_headers={},
        request_headers={"x-region": "EU", "brand": "S", "x-appbrand": "S"},
        vin_headers=("VIN",),
        response_envelope="",
        auth_headers={"brand": "S", "x-appbrand": "S"},
    )


def _subaru_na() -> RegionConfig:
    return RegionConfig(
        name="Subaru NA",
        auth_realm="https://login.subarudriverslogin.com/oauth2/realms/root/realms/tmna-native",
        api_base_url="https://api.telematicsct.com",
        client_id="oneappsdkclient",
        redirect_uri="com.toyota.oneapp:/oauth2Callback",
        basic_auth="b25lYXBwOm9uZWFwcA==",
        api_key="pypIHG015k4ABHWbcI4G0a94F7cC0JDo1OynpAsG",
        brand="S",
        region="NA",
        auth_service="",
        endpoints=dict(_ENDPOINTS_NA),
        endpoint_headers={"telemetry": {"GENERATION": "17CYPLUS"}},
        request_headers={"x-region": "US", "X-LOCALE": "en-US"},
        vin_headers=("VIN", "vin"),
        response_envelope="payload",
        auth_headers={},
        post_processors={"electric_status": "normalize_na_electric"},
        fallbacks={"location": "location_from_vehicle_status"},
    )


_DEFAULTS = {
    "subaru-eu": _subaru_eu(),
    "subaru-na": _subaru_na(),
    "toyota-eu": _toyota_eu(),
    "toyota-na": _toyota_na(),
    "lexus-eu":  _lexus_eu(),
    "lexus-na":  _lexus_na(),
}


def _load_regions() -> dict:
    """Load region configs: built-in defaults, deep-merged with regions.json overrides."""
    regions = dict(_DEFAULTS)
    _alias = {"eu": "subaru-eu", "na": "subaru-na"}

    config_path = DATA_DIR / "regions.json"
    if config_path.exists():
        try:
            user_config = json.loads(config_path.read_text())
            for region_name, overrides in user_config.items():
                resolved = _alias.get(region_name.lower(), region_name)
                if resolved in regions:
                    base = {f.name: getattr(regions[resolved], f.name) for f in fields(RegionConfig)}
                    # Dict-typed fields merge element-wise so users can override a single endpoint or header.
                    for k, v in overrides.items():
                        if isinstance(v, dict) and isinstance(base.get(k), dict):
                            merged = dict(base[k])
                            merged.update(v)
                            base[k] = merged
                        else:
                            base[k] = v
                    regions[resolved] = RegionConfig(**base)
                else:
                    regions[region_name] = RegionConfig(**overrides)
        except Exception as e:
            print(f"Warning: Could not load {config_path}: {e}")

    # Backward-compat aliases for legacy uppercase keys
    if "subaru-eu" in regions and "EU" not in regions:
        regions["EU"] = regions["subaru-eu"]
    if "subaru-na" in regions and "NA" not in regions:
        regions["NA"] = regions["subaru-na"]
    return regions


REGIONS = _load_regions()
