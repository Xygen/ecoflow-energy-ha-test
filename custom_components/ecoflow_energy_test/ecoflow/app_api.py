"""EcoFlow App API client (async) - token-based authentication.

Provides login via email/password, device discovery, and MQTT credential
retrieval using the EcoFlow Portal API. No IoT Developer API keys required.
Uses aiohttp for async HTTP - HA provides the ClientSession.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import IOT_API_BASE, get_device_type
from .enhanced_auth import enhanced_login, get_enhanced_credentials

_LOGGER = logging.getLogger(__name__)

_DEVICE_LIST_PATH = "/iot-service/user/device"
_PROVIDER_DEVICE_LIST_PATH = "/provider-service/user/device/list"
_DEVICE_DETAIL_PATH = "/provider-service/user/device/detail"
_POWEROCEAN_PRODUCT_TYPES = frozenset({"83", "85", "86", "87"})


class AppApiClient:
    """EcoFlow App API - token-authenticated async client.

    Uses email/password login to obtain a JWT token, then fetches
    device lists and MQTT credentials without Developer API keys.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._user_id: str | None = None
        self._base_url: str = IOT_API_BASE
        self._consumer_base_url: str | None = None

    @property
    def token(self) -> str | None:
        """Return the current JWT token, or None if not logged in."""
        return self._token

    @property
    def user_id(self) -> str | None:
        """Return the current user ID, or None if not logged in."""
        return self._user_id

    async def login(self) -> bool:
        """Login via email/password and store JWT token + user ID.

        Delegates to enhanced_auth.enhanced_login which handles
        multi-region fallback (EU + global).

        Returns True on success, False on failure.
        """
        result = await enhanced_login(self._session, self._email, self._password)
        if result is None:
            self._token = None
            self._user_id = None
            return False

        self._token = result["token"]
        self._user_id = result["user_id"]
        # Remember the host that accepted the login so subsequent calls
        # (device list, MQTT credentials) hit the same region.
        self._base_url = result.get("base_url", IOT_API_BASE)
        _LOGGER.debug("App login OK (user_id=%s, base_url=%s)", self._user_id, self._base_url)
        return True

    async def get_device_list(self) -> list[dict[str, Any]]:
        """Fetch the list of bound and shared devices.

        Returns a normalized list of device dicts compatible with
        IoTApiClient format:
            [{"sn": "...", "product_name": "...", "product_type": "85",
              "online": 1, "device_type": "..."}, ...]

        Returns an empty list on failure.
        """
        if not self._token:
            _LOGGER.debug("App API: no token, cannot fetch device list")
            return []

        url = f"{self._base_url}{_DEVICE_LIST_PATH}"
        headers = {"Authorization": f"Bearer {self._token}"}

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self._session.get(url, headers=headers, timeout=timeout) as resp:
                resp.raise_for_status()
                body = await resp.json()

                if str(body.get("code")) != "0":
                    _LOGGER.warning(
                        "App API device list: code=%s msg=%s",
                        body.get("code"),
                        body.get("message"),
                    )
                    return []

                data = body.get("data", {})
                if not isinstance(data, dict):
                    _LOGGER.debug("App API device list: unexpected data format")
                    return []

                return _parse_device_response(data)

        except (aiohttp.ClientError, TimeoutError) as exc:
            _LOGGER.warning("App API device list failed: %s", exc)
            return []

    async def get_mqtt_credentials(self) -> dict[str, Any] | None:
        """Fetch Enhanced Mode MQTT credentials using the stored token.

        Delegates to enhanced_auth.get_enhanced_credentials for
        AES-CFB decryption of the Portal certification endpoint.

        Returns the MQTT credentials dict or None on failure.
        """
        if not self._token:
            _LOGGER.debug("App API: no token, cannot fetch MQTT credentials")
            return None

        return await get_enhanced_credentials(self._session, self._token, base_url=self._base_url)

    async def get_powerocean_devices(self) -> list[dict[str, str]]:
        """Return PowerOcean parents available to the consumer detail API.

        PowerGlow is exposed as report data below its PowerOcean parent.  The
        provider endpoint supplies both the parent serial number and the
        required ``product-type`` header value.
        """
        if not self._token:
            return []

        headers = {"Authorization": f"Bearer {self._token}"}
        for base_url in self._consumer_base_urls():
            url = f"{base_url}{_PROVIDER_DEVICE_LIST_PATH}"
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with self._session.get(url, headers=headers, timeout=timeout) as resp:
                    resp.raise_for_status()
                    devices = _parse_provider_device_response(await resp.json())
                    if devices:
                        self._consumer_base_url = base_url
                        return devices
            except (aiohttp.ClientError, TimeoutError) as exc:
                _LOGGER.debug("App API provider device list via %s failed: %s", base_url, exc)
        return []

    async def get_device_detail(
        self,
        serial_number: str,
        product_type: str = "",
    ) -> dict[str, Any] | None:
        """Fetch the read-only consumer detail report for a PowerOcean parent."""
        if not self._token or not serial_number:
            return None

        headers = {"Authorization": f"Bearer {self._token}"}
        if product_type:
            headers["product-type"] = str(product_type)
        for base_url in self._consumer_base_urls():
            url = f"{base_url}{_DEVICE_DETAIL_PATH}"
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with self._session.get(
                    url,
                    params={"sn": serial_number},
                    headers=headers,
                    timeout=timeout,
                ) as resp:
                    resp.raise_for_status()
                    body = await resp.json()
                    if not isinstance(body, dict) or not isinstance(body.get("data"), dict):
                        continue
                    code = body.get("code")
                    if code is not None and str(code) != "0":
                        _LOGGER.debug(
                            "App API device detail via %s: code=%s msg=%s",
                            base_url,
                            code,
                            body.get("message"),
                        )
                        continue
                    self._consumer_base_url = base_url
                    return body
            except (aiohttp.ClientError, TimeoutError) as exc:
                _LOGGER.debug("App API device detail via %s failed: %s", base_url, exc)
        _LOGGER.debug("App API device detail failed for %s", serial_number[:4])
        return None

    def _consumer_base_urls(self) -> tuple[str, ...]:
        """Return regional consumer API hosts in the best-known order."""
        candidates = (
            self._consumer_base_url,
            self._base_url,
            IOT_API_BASE,
            "https://api-a.ecoflow.com",
        )
        return tuple(dict.fromkeys(url for url in candidates if url))


def _parse_device_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Portal API device response into normalized device list.

    The Portal API returns devices grouped by ownership:
        {"bound": {SN: {deviceInfo}}, "share": {SN: {deviceInfo}}, ...}

    Each group can also contain list-based formats:
        {"bound": {groupKey: [deviceInfo, ...]}}

    We normalize all formats into a flat list with consistent field names.
    """
    devices: list[dict[str, Any]] = []
    seen_sns: set[str] = set()

    for category in ("bound", "share"):
        group = data.get(category, {})
        if not isinstance(group, dict):
            continue

        for key, value in group.items():
            if isinstance(value, list):
                # Format: {groupKey: [device, device, ...]}
                for dev in value:
                    _add_device(dev, devices, seen_sns)
            elif isinstance(value, dict):
                # Format: {SN: {deviceInfo}} - key is the serial number
                dev = value
                if "sn" not in dev:
                    dev = {**dev, "sn": key}
                _add_device(dev, devices, seen_sns)

    return devices


def _add_device(
    dev: dict[str, Any],
    devices: list[dict[str, Any]],
    seen_sns: set[str],
) -> None:
    """Normalize a single device dict and append to the list.

    Deduplicates by serial number (a device can appear in both bound and share).
    """
    sn = dev.get("sn", "")
    if not sn or sn in seen_sns:
        return

    seen_sns.add(sn)
    product_name = dev.get("productName", dev.get("name", ""))

    devices.append({
        "sn": sn,
        "product_name": product_name,
        "product_type": str(dev.get("productType", dev.get("product_type", "")) or ""),
        "online": dev.get("online", 0),
        "device_type": get_device_type(product_name, sn),
    })


def _parse_provider_device_response(response: dict[str, Any]) -> list[dict[str, str]]:
    """Normalize the provider device-list shapes used by EcoFlow regions."""
    data: Any = response.get("data", [])
    if isinstance(data, dict):
        data = data.get("devices", data.get("list", []))
    if not isinstance(data, list):
        return []

    devices: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        serial_number = str(item.get("sn", "") or "")
        product_type = str(item.get("productType", item.get("product_type", "")) or "")
        if serial_number and product_type in _POWEROCEAN_PRODUCT_TYPES:
            devices.append({
                "sn": serial_number,
                "product_type": product_type,
                "name": str(item.get("deviceName", item.get("name", serial_number))),
            })
    return devices
