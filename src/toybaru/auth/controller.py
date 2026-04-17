"""OAuth2 authentication controller for Toyota/Subaru Connected Services.

Implements the 3-stage ForgeRock AM OAuth2 flow:
1. Authenticate: POST credentials via callbacks -> get tokenId
2. Authorize: GET with iPlanetDirectoryPro cookie -> get auth code
3. Token: POST auth code -> get access/refresh/id tokens

"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets as _secrets
import uuid
from base64 import urlsafe_b64encode
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt

from toybaru.const import CLIENT_VERSION, DATA_DIR, USER_AGENT, RegionConfig
from toybaru.exceptions import AuthenticationError, OtpRequiredError, TokenExpiredError
from toybaru.http import make_client


TOKEN_FILE = DATA_DIR / "tokens.json"


@dataclass
class TokenInfo:
    access_token: str
    refresh_token: str
    uuid: str
    expires_at: float  # UTC timestamp

    @property
    def is_valid(self) -> bool:
        return self.expires_at > datetime.now(timezone.utc).timestamp()


class AuthController:
    """Handles authentication with the Toyota/Subaru connected services backend."""

    def __init__(self, region: RegionConfig, username: str, password: str) -> None:
        self.region = region
        self._username = username
        self._password = password
        self._token_info: TokenInfo | None = None
        self._code_verifier: str | None = None
        self._pending_otp: dict | None = None
        self._auth_lock = asyncio.Lock()
        self._load_saved_tokens()

    @property
    def token(self) -> str | None:
        return self._token_info.access_token if self._token_info else None

    @property
    def uuid(self) -> str | None:
        return self._token_info.uuid if self._token_info else None

    @property
    def is_authenticated(self) -> bool:
        return self._token_info is not None and self._token_info.is_valid

    @property
    def otp_pending(self) -> bool:
        return self._pending_otp is not None

    @staticmethod
    def _generate_pkce() -> tuple[str, str]:
        """Generate PKCE S256 code_verifier and code_challenge."""
        verifier = urlsafe_b64encode(_secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return verifier, challenge

    async def ensure_token(self) -> str:
        """Ensure we have a valid access token, refreshing or re-authenticating as needed."""
        async with self._auth_lock:
            if self._token_info and self._token_info.is_valid:
                return self._token_info.access_token

            if self._token_info and self._token_info.refresh_token:
                try:
                    await self._refresh_tokens()
                    return self._token_info.access_token
                except (AuthenticationError, httpx.HTTPError):
                    pass  # Fall through to full auth

            await self._authenticate()
            return self._token_info.access_token

    async def _authenticate(self) -> None:
        """Full 3-stage authentication flow."""
        self._code_verifier, code_challenge = self._generate_pkce()
        async with make_client(timeout=30, follow_redirects=False) as client:
            # Stage 1: Authenticate
            token_id, cookies = await self._perform_authentication(client)

            # Stage 2: Authorize
            auth_code = await self._perform_authorization(client, token_id, cookies, code_challenge)

            # Stage 3: Token exchange
            token_data = await self._retrieve_tokens(client, auth_code)

            self._update_tokens(token_data)

    async def _perform_authentication(self, client: httpx.AsyncClient) -> tuple[str, list[tuple]]:
        """Stage 1: Submit credentials via ForgeRock callbacks, get tokenId."""
        auth_base = self.region.auth_realm.replace('oauth2', 'json')
        auth_url = f"{auth_base}/authenticate"
        if self.region.auth_service:
            auth_url += f"?authIndexType=service&authIndexValue={self.region.auth_service}"

        headers = {
            "Accept-API-Version": "resource=2.1, protocol=1.0",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Region": self.region.region,
            "Region": self.region.region,
            "Brand": self.region.brand,
            "X-Brand": self.region.brand,
            "User-Agent": USER_AGENT,
        }

        # Build initial data
        if not self.region.auth_service:
            data: dict[str, Any] = {
                "callbacks": [{
                    "type": "NameCallback",
                    "input": [{"name": "IDToken1", "value": "en-US"}],
                    "output": [{"name": "prompt", "value": "ui_locales"}],
                }]
            }
        else:
            data = {}

        token_id = await self._run_callback_loop(client, auth_url, headers, data)
        # Collect cookies as list of tuples (name, value, domain, path)
        cookies: list[tuple] = []
        for cookie in client.cookies.jar:
            cookies.append((cookie.name, cookie.value, cookie.domain, cookie.path))
        return token_id, cookies

    async def _run_callback_loop(
        self,
        client: httpx.AsyncClient,
        auth_url: str,
        headers: dict[str, str],
        data: dict[str, Any],
    ) -> str:
        """Process ForgeRock callback rounds until tokenId is obtained."""
        for _ in range(10):
            if "callbacks" in data:
                for cb in data["callbacks"]:
                    cb_type = cb["type"]
                    prompt = cb["output"][0].get("value", "") if cb.get("output") else ""
                    cb_id = cb.get("_id", "")

                    if cb_type == "NameCallback" and "User Name" in prompt:
                        cb["input"][0]["value"] = self._username
                    elif cb_type == "NameCallback" and prompt in ("Market Locale", "Internationalization", "UI Locales", "ui_locales"):
                        cb["input"][0]["value"] = "en-US"
                    elif cb_type == "HiddenValueCallback" and cb_id == "devicePrint":
                        app_id = self.region.redirect_uri.split(":/")[0] if "://" not in self.region.redirect_uri else self.region.redirect_uri.split("://")[0]
                        device_print = json.dumps({
                            "appId": app_id,
                            "deviceType": "Android",
                            "hardwareId": uuid.uuid4().hex,
                            "model": "sdk_gphone64_x86_64",
                            "systemOS": "14",
                        })
                        cb["input"][0]["value"] = device_print
                    elif cb_type == "PasswordCallback" and "One Time Password" in prompt:
                        # OTP required — pause and let caller provide code
                        cookies: list[tuple] = []
                        for cookie in client.cookies.jar:
                            cookies.append((cookie.name, cookie.value, cookie.domain, cookie.path))
                        self._pending_otp = {
                            "auth_url": auth_url,
                            "headers": headers,
                            "data": data,
                            "cookies": cookies,
                        }
                        raise OtpRequiredError("OTP code required")
                    elif cb_type == "PasswordCallback":
                        cb["input"][0]["value"] = self._password
                    elif cb_type == "ChoiceCallback":
                        cb["input"][0]["value"] = 0
                    elif cb_type == "ConfirmationCallback":
                        cb["input"][0]["value"] = 0
                    elif cb_type == "TextOutputCallback" and "Not Found" in str(prompt):
                        raise AuthenticationError(f"User not found: {prompt}")

            resp = await client.post(auth_url, json=data, headers=headers)
            if resp.status_code != 200:
                raise AuthenticationError(f"Authentication failed (HTTP {resp.status_code})")

            data = resp.json()
            if "tokenId" in data:
                return data["tokenId"]

        raise AuthenticationError("No tokenId received after multiple callback rounds.")

    async def submit_otp(self, code: str) -> None:
        """Submit OTP code and complete authentication."""
        if not self._pending_otp:
            raise AuthenticationError("No pending OTP session")

        pending = self._pending_otp
        self._pending_otp = None

        auth_url = pending["auth_url"]
        headers = pending["headers"]
        data = pending["data"]
        saved_cookies = pending["cookies"]

        # Fill in the OTP code
        for cb in data.get("callbacks", []):
            if cb["type"] == "PasswordCallback":
                prompt = cb["output"][0].get("value", "") if cb.get("output") else ""
                if "One Time Password" in prompt:
                    cb["input"][0]["value"] = code

        self._code_verifier, code_challenge = self._generate_pkce()

        async with make_client(timeout=30, follow_redirects=False) as client:
            # Restore cookies
            for name, value, domain, path in saved_cookies:
                client.cookies.set(name, value, domain=domain)

            # Continue callback loop (submit OTP)
            resp = await client.post(auth_url, json=data, headers=headers)
            if resp.status_code != 200:
                raise AuthenticationError(f"Authentication failed (HTTP {resp.status_code})")

            result = resp.json()
            if "tokenId" in result:
                token_id = result["tokenId"]
            else:
                # More callbacks — continue the loop
                token_id = await self._run_callback_loop(client, auth_url, headers, result)

            # Collect cookies
            cookies: list[tuple] = []
            for cookie in client.cookies.jar:
                cookies.append((cookie.name, cookie.value, cookie.domain, cookie.path))

            auth_code = await self._perform_authorization(client, token_id, cookies, code_challenge)
            token_data = await self._retrieve_tokens(client, auth_code)
            self._update_tokens(token_data)

    async def _perform_authorization(
        self,
        client: httpx.AsyncClient,
        token_id: str,
        cookies: list[tuple] | None = None,
        code_challenge: str | None = None,
    ) -> str:
        """Stage 2: Exchange tokenId for authorization code via redirect."""
        challenge = code_challenge or "plain"
        challenge_method = "S256" if code_challenge and code_challenge != "plain" else "plain"
        authorize_url = (
            f"{self.region.auth_realm}/authorize"
            f"?client_id={self.region.client_id}"
            f"&scope=openid+profile+write"
            f"&response_type=code"
            f"&redirect_uri={self.region.redirect_uri}"
            f"&code_challenge={challenge}"
            f"&code_challenge_method={challenge_method}"
        )
        cookie_header = f"iPlanetDirectoryPro={token_id}"
        if cookies:
            extras = "; ".join(f"{n}={v}" for n, v, _, _ in cookies if n != "iPlanetDirectoryPro")
            if extras:
                cookie_header += f"; {extras}"

        headers = {
            "Accept-API-Version": "resource=2.1, protocol=1.0",
            "Cookie": cookie_header,
            "User-Agent": USER_AGENT,
        }

        resp = await client.get(authorize_url, headers=headers)
        if resp.status_code != 302:
            raise AuthenticationError(f"Authorization failed (HTTP {resp.status_code})")

        location = resp.headers.get("location", "")
        parsed = parse_qs(urlparse(location).query)
        if "code" not in parsed:
            raise AuthenticationError(f"No auth code in redirect: {location}")

        return parsed["code"][0]

    async def _retrieve_tokens(self, client: httpx.AsyncClient, auth_code: str) -> dict[str, Any]:
        """Stage 3: Exchange authorization code for access/refresh tokens."""
        token_url = f"{self.region.auth_realm}/access_token"

        token_headers: dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        }
        if self.region.basic_auth:
            token_headers["Authorization"] = f"Basic {self.region.basic_auth}"

        token_data = {
            "client_id": self.region.client_id,
            "code": auth_code,
            "redirect_uri": self.region.redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": self._code_verifier or "plain",
        }

        resp = await client.post(token_url, headers=token_headers, data=token_data)
        if resp.status_code != 200:
            raise AuthenticationError(f"Token exchange failed (HTTP {resp.status_code})")

        return resp.json()

    async def _refresh_tokens(self) -> None:
        """Refresh access token using refresh token."""
        token_url = f"{self.region.auth_realm}/access_token"

        refresh_headers: dict[str, str] = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        }
        if self.region.basic_auth:
            refresh_headers["Authorization"] = f"Basic {self.region.basic_auth}"

        async with make_client(timeout=30) as client:
            resp = await client.post(
                token_url,
                headers=refresh_headers,
                data={
                    "client_id": self.region.client_id,
                    "redirect_uri": self.region.redirect_uri,
                    "grant_type": "refresh_token",
                    "refresh_token": self._token_info.refresh_token,
                },
            )
            if resp.status_code != 200:
                raise AuthenticationError(f"Token refresh failed (HTTP {resp.status_code})")

            self._update_tokens(resp.json())

    def _update_tokens(self, data: dict[str, Any]) -> None:
        """Parse token response and persist."""
        for field in ("access_token", "id_token", "refresh_token", "expires_in"):
            if field not in data:
                raise AuthenticationError(f"Missing field in token response: {field}")

        claims = jwt.decode(
            data["id_token"],
            algorithms=["RS256"],
            options={"verify_signature": False, "verify_aud": False},
        )
        # Fallback through uuid -> extension_tmsguid -> sub
        user_uuid = claims.get("uuid") or claims.get("extension_tmsguid") or claims.get("sub")
        if not user_uuid:
            raise AuthenticationError("No user identifier in id_token")

        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])).timestamp()

        self._token_info = TokenInfo(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            uuid=user_uuid,
            expires_at=expires_at,
        )
        self._save_tokens()

    def _save_tokens(self) -> None:
        """Persist tokens to disk."""
        if not self._token_info:
            return
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps(asdict(self._token_info), indent=2))

    def _load_saved_tokens(self) -> None:
        """Load tokens from disk if available."""
        if TOKEN_FILE.exists():
            try:
                data = json.loads(TOKEN_FILE.read_text())
                self._token_info = TokenInfo(**data)
            except (json.JSONDecodeError, TypeError, KeyError):
                pass  # Corrupted file, ignore

    def clear_tokens(self) -> None:
        """Remove saved tokens."""
        self._token_info = None
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
