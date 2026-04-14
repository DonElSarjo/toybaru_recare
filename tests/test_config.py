"""Tests for config/region loading."""

import json
from unittest.mock import patch
from pathlib import Path

from toybaru.const import RegionConfig, _load_regions, _DEFAULTS, DATA_DIR


def test_default_regions():
    regions = _load_regions()
    assert "subaru-eu" in regions
    assert "subaru-na" in regions
    assert "toyota-eu" in regions
    assert "toyota-na" in regions
    # Backward compat aliases
    assert "EU" in regions
    assert "NA" in regions
    assert regions["subaru-eu"].brand == "S"
    assert regions["toyota-eu"].brand == "T"
    assert "toyota-europe" in regions["subaru-eu"].auth_realm
    assert "subarudriverslogin" in regions["subaru-na"].auth_realm
    assert "toyotadriverslogin" in regions["toyota-na"].auth_realm


def test_custom_regions_json(tmp_path):
    config = {"subaru-eu": {"api_key": "my-custom-key"}}
    (tmp_path / "regions.json").write_text(json.dumps(config))
    with patch("toybaru.const.DATA_DIR", tmp_path):
        regions = _load_regions()
    assert regions["subaru-eu"].api_key == "my-custom-key"
    assert "toyota-europe" in regions["subaru-eu"].auth_realm


def test_custom_regions_merge(tmp_path):
    config = {"subaru-eu": {"client_id": "custom-client"}}
    (tmp_path / "regions.json").write_text(json.dumps(config))
    with patch("toybaru.const.DATA_DIR", tmp_path):
        regions = _load_regions()
    assert regions["subaru-eu"].client_id == "custom-client"
    assert regions["subaru-eu"].name == "Subaru EU"
    assert regions["subaru-eu"].brand == "S"


def test_new_region(tmp_path):
    config = {"jp": {
        "name": "JP", "auth_realm": "https://jp.example.com", "api_base_url": "https://api.jp.example.com",
        "client_id": "jp-client", "redirect_uri": "com.jp.app:/callback", "basic_auth": "abc123",
        "api_key": "jp-key", "brand": "S", "region": "JP",
    }}
    (tmp_path / "regions.json").write_text(json.dumps(config))
    with patch("toybaru.const.DATA_DIR", tmp_path):
        regions = _load_regions()
    assert "jp" in regions
    assert regions["jp"].api_base_url == "https://api.jp.example.com"
    assert "subaru-eu" in regions
