"""Tests for OTP (SMS 2FA) authentication flow."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from toybaru.auth.controller import AuthController
from toybaru.const import RegionConfig
from toybaru.exceptions import AuthenticationError, OtpRequiredError


def _na_region() -> RegionConfig:
    """NA region config for testing."""
    return RegionConfig(
        name="NA",
        auth_realm="https://login.example.com/oauth2/realms/root/realms/tmna-native",
        api_base_url="https://api.example.com",
        client_id="testclient",
        redirect_uri="com.test.app:/callback",
        basic_auth="dGVzdDp0ZXN0",
        api_key="test-api-key",
        brand="S",
        region="NA",
        auth_service="",
    )


def _make_callback_response(callbacks, auth_id="auth-id-123"):
    """Build a ForgeRock callback response."""
    return {"authId": auth_id, "callbacks": callbacks}


def _name_callback(prompt, value=""):
    return {
        "type": "NameCallback",
        "input": [{"name": "IDToken1", "value": value}],
        "output": [{"name": "prompt", "value": prompt}],
    }


def _password_callback(prompt, value=""):
    return {
        "type": "PasswordCallback",
        "input": [{"name": "IDToken1", "value": value}],
        "output": [{"name": "prompt", "value": prompt}],
    }


def _confirmation_callback(options=None):
    """Build a ConfirmationCallback (e.g. Verify/Resend OTP)."""
    if options is None:
        options = ["Verify OTP", "Resend OTP"]
    return {
        "type": "ConfirmationCallback",
        "input": [{"name": "IDToken3", "value": 0}],
        "output": [
            {"name": "prompt", "value": ""},
            {"name": "options", "value": options},
        ],
    }


def _token_response():
    """Final tokenId response from ForgeRock."""
    return {"tokenId": "sso-token-xyz", "successUrl": "/console"}


def _oauth_tokens():
    """OAuth token exchange response."""
    # Minimal JWT for id_token with a uuid claim
    import jwt as pyjwt
    id_token = pyjwt.encode({"uuid": "user-uuid-abc", "aud": "oneappsdkclient"}, "secret", algorithm="HS256")
    return {
        "access_token": "access-token-123",
        "refresh_token": "refresh-token-456",
        "id_token": id_token,
        "expires_in": 3600,
    }


# --- AuthController OTP tests ---

class TestAuthControllerOtp:

    def _make_controller(self) -> AuthController:
        with patch("toybaru.auth.controller.TOKEN_FILE") as mock_file:
            mock_file.exists.return_value = False
            return AuthController(_na_region(), "user@test.com", "password123")

    @pytest.mark.asyncio
    async def test_otp_callback_raises_otp_required(self):
        """When ForgeRock sends an OTP callback, OtpRequiredError is raised."""
        ctrl = self._make_controller()

        # Simulate: round 1 = locale, round 2 = username, round 3 = password, round 4 = OTP
        otp_cbs = [
            _password_callback("One Time Password"),
            _confirmation_callback(),
        ]
        responses = [
            _make_callback_response([_name_callback("User Name")]),
            _make_callback_response([_password_callback("Password")]),
            _make_callback_response(otp_cbs),
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = responses[min(call_count, len(responses) - 1)]
            call_count += 1
            return resp

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.cookies = MagicMock()
        mock_client.cookies.jar = []

        with pytest.raises(OtpRequiredError):
            await ctrl._run_callback_loop(
                mock_client,
                "https://example.com/authenticate",
                {"Content-Type": "application/json"},
                {"callbacks": [_name_callback("ui_locales", "en-US")]},
            )

        # Verify pending state was saved
        assert ctrl._pending_otp is not None
        assert "auth_url" in ctrl._pending_otp
        assert "data" in ctrl._pending_otp

    @pytest.mark.asyncio
    async def test_submit_otp_completes_auth(self):
        """submit_otp fills in the code and completes the auth flow."""
        ctrl = self._make_controller()

        # Pre-set pending OTP state as if OtpRequiredError was just raised
        ctrl._pending_otp = {
            "auth_url": "https://example.com/authenticate",
            "headers": {"Content-Type": "application/json"},
            "data": _make_callback_response([_password_callback("One Time Password")]),
            "cookies": [("session_cookie", "abc123", "example.com", "/")],
        }

        tokens = _oauth_tokens()

        async def mock_post(url, **kwargs):
            resp = MagicMock()
            if "/authenticate" in url:
                resp.status_code = 200
                resp.json.return_value = _token_response()
            elif "/access_token" in url:
                resp.status_code = 200
                resp.json.return_value = tokens
            return resp

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 302
            resp.headers = {"location": "com.test.app:/callback?code=auth-code-789"}
            return resp

        with patch("toybaru.auth.controller.make_client") as mock_make:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.get = mock_get
            mock_client.cookies = MagicMock()
            mock_client.cookies.set = MagicMock()

            ctx = AsyncMock()
            ctx.__aenter__ = AsyncMock(return_value=mock_client)
            ctx.__aexit__ = AsyncMock(return_value=False)
            mock_make.return_value = ctx

            with patch("toybaru.auth.controller.TOKEN_FILE") as mock_tf:
                mock_tf.exists.return_value = False
                await ctrl.submit_otp("123456")

        assert ctrl._pending_otp is None
        assert ctrl.is_authenticated
        assert ctrl.uuid == "user-uuid-abc"

    @pytest.mark.asyncio
    async def test_submit_otp_without_pending_raises(self):
        """submit_otp raises AuthenticationError if no OTP is pending."""
        ctrl = self._make_controller()
        with pytest.raises(AuthenticationError, match="No pending OTP"):
            await ctrl.submit_otp("123456")

    @pytest.mark.asyncio
    async def test_otp_pending_property(self):
        """otp_pending property reflects state correctly."""
        ctrl = self._make_controller()
        assert ctrl.otp_pending is False

        ctrl._pending_otp = {"auth_url": "test", "headers": {}, "data": {}, "cookies": []}
        assert ctrl.otp_pending is True


# --- Web API OTP tests ---

class TestWebOtp:

    def test_login_otp_no_session(self):
        """POST /api/login/otp without a valid session returns error."""
        from fastapi.testclient import TestClient
        from toybaru.web import app

        client = TestClient(app)
        resp = client.post("/api/login/otp", json={"otp_session": "bad", "code": "123"})
        assert resp.status_code == 400
        assert "expired" in resp.json()["error"].lower() or "invalid" in resp.json()["error"].lower()

    def test_login_otp_missing_params(self):
        """POST /api/login/otp with missing params returns 400."""
        from fastapi.testclient import TestClient
        from toybaru.web import app

        client = TestClient(app)
        resp = client.post("/api/login/otp", json={})
        assert resp.status_code == 400

    def test_login_returns_needs_otp(self):
        """POST /api/login returns needs_otp when OtpRequiredError is raised."""
        from fastapi.testclient import TestClient
        from toybaru.web import app, _otp_pending

        with patch("toybaru.web.ToybaruClient") as MockClient:
            instance = MockClient.return_value
            instance.login = AsyncMock(side_effect=OtpRequiredError())
            instance.auth = MagicMock()
            instance.auth.otp_pending = True

            client = TestClient(app)
            resp = client.post("/api/login", json={
                "username": "test@test.com", "password": "pw", "region": "EU",
            })

        data = resp.json()
        assert data["needs_otp"] is True
        assert "otp_session" in data

        # Clean up
        _otp_pending.clear()
