"""HTTP quota polling for the EcoFlow device coordinator."""

from __future__ import annotations

import logging
import time
from typing import Any

from ..const import (
    DEVICE_TYPE_DELTA,
    DEVICE_TYPE_DELTA3,
    DEVICE_TYPE_POWEROCEAN,
    DEVICE_TYPE_POWERGLOW,
    DEVICE_TYPE_SMARTPLUG,
    DEVICE_TYPE_STREAM,
)
from ..ecoflow.parsers.delta_http import parse_delta_http_quota
from ..ecoflow.parsers.delta3_http import parse_delta3_http_quota
from ..ecoflow.parsers.powerocean import parse_powerocean_http_quota
from ..ecoflow.parsers.powerglow import (
    extract_powerglow_reports,
    parse_powerglow_detail_response,
    parse_powerglow_quota,
)
from ..ecoflow.parsers.smartplug import parse_smartplug_http_quota
from ..ecoflow.parsers.stream_http import parse_stream_quota

_LOGGER = logging.getLogger(__name__)
_POWERGLOW_PARENT_DISCOVERY_INTERVAL_S = 300.0


class HttpPollMixin:
    """Mixin providing the HTTP polling update path."""

    # ------------------------------------------------------------------
    # HTTP fallback (called when MQTT is stale)
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """HTTP polling — primary source in Standard Mode, fallback in Enhanced.

        PowerOcean: POST /iot-open/sign/device/quota (with quotas array)
        Delta:      GET  /iot-open/sign/device/quota/all?sn=...
        """
        from .core import DeviceSnapshot

        if (
            self.device_type == DEVICE_TYPE_POWERGLOW
            and self._app_api is not None
            and not self._powerglow_parent_devices
            and (
                self._last_powerglow_parent_discovery_ts <= 0
                or time.monotonic() - self._last_powerglow_parent_discovery_ts
                >= _POWERGLOW_PARENT_DISCOVERY_INTERVAL_S
            )
        ):
            await self._discover_powerglow_parent_devices()

        app_detail_poll = (
            self.device_type == DEVICE_TYPE_POWERGLOW
            and self._app_api is not None
            and bool(self._powerglow_parent_devices)
        )
        if self._http_client is None and not app_detail_poll:
            return self._device_data

        # All device types use GET /quota/all — returns the most complete data
        source = "http"
        parsed_detail: dict[str, Any] | None = None
        raw: dict[str, Any] | None = None
        if app_detail_poll:
            source = "app_detail"
            for parent in self._powerglow_parent_devices:
                candidate = await self._app_api.get_device_detail(
                    parent["sn"], parent["product_type"]
                )
                if not candidate:
                    continue
                candidate_parsed = parse_powerglow_detail_response(
                    candidate, self.device_sn
                )
                if candidate_parsed:
                    raw = candidate
                    parsed_detail = candidate_parsed
                    break
        else:
            raw = await self._http_client.get_quota_all()
        if not raw:
            error_code = (
                self._http_client.last_error_code
                if self._http_client is not None
                else None
            )

            # Error 1006 = device not linked to API key — config issue, not auth (#2)
            if error_code == "1006":
                self._log_event("http_1006", "device not linked to API key")
                return dict(self._device_data)

            self._consecutive_http_failures += 1
            self._log_event(
                f"{source}_fail", f"consecutive={self._consecutive_http_failures}"
            )
            if self._consecutive_http_failures >= 3 and not app_detail_poll:
                self._device_available = False
                self._snapshot = DeviceSnapshot(
                    data={},
                    captured_at=self._snapshot.captured_at,
                    source=self._snapshot.source,
                    key_count=0,
                )

            # In Enhanced Mode, only trigger reauth if MQTT has never delivered data.
            # When MQTT is active, HTTP failures are expected fallback noise (#2).
            mqtt_active = self._enhanced_mode and self._last_mqtt_ts > 0.0
            if (
                self._consecutive_http_failures == 5
                and not mqtt_active
                and not app_detail_poll
            ):
                _LOGGER.warning(
                    "HTTP quota failed %d consecutive times for %s — triggering re-authentication",
                    self._consecutive_http_failures, self.device_sn,
                )
                self._entry.async_start_reauth(self.hass)
            return dict(self._device_data)

        self._consecutive_http_failures = 0
        self._device_available = True
        self._log_event(f"{source}_ok", f"keys={len(raw)}")

        if self.device_type == DEVICE_TYPE_POWEROCEAN:
            parsed = parse_powerocean_http_quota(raw)
        elif self.device_type == DEVICE_TYPE_POWERGLOW:
            self._raw_quota = extract_powerglow_reports(raw) or dict(raw)
            self._raw_quota_captured_at = time.monotonic()
            parsed = parsed_detail or parse_powerglow_quota(raw)
            if source == "app_detail":
                self._last_cloud_ts = time.monotonic()
        elif self.device_type == DEVICE_TYPE_DELTA:
            parsed = parse_delta_http_quota(raw)
        elif self.device_type == DEVICE_TYPE_DELTA3:
            # Keep the raw quota snapshot for diagnostics: the Delta 3 field
            # map is community-researched but not yet hardware-verified for
            # every key, so the raw key names let beta dumps confirm and
            # extend the mapping.
            self._raw_quota = dict(raw)
            self._raw_quota_captured_at = time.monotonic()
            parsed = parse_delta3_http_quota(raw)
        elif self.device_type == DEVICE_TYPE_SMARTPLUG:
            parsed = parse_smartplug_http_quota(raw)
        elif self.device_type == DEVICE_TYPE_STREAM:
            # Standard mode delivers flat camelCase JSON. Keep the raw
            # snapshot for diagnostics: the field map covers the keys seen on
            # Stream Ultra / Ultra X so far, and beta dumps are what extends
            # it (#139).
            self._raw_quota = dict(raw)
            self._raw_quota_captured_at = time.monotonic()
            parsed = parse_stream_quota(raw)
        else:
            parsed = raw
        self._enforce_monotonic(parsed)
        # Same pop as in _apply_data: prevent EMS raw battery state from
        # overwriting the power-derived value (#50).
        parsed.pop("batt_charge_discharge_state", None)
        self._device_data.update(parsed)

        # Derive battery state from power (same logic as MQTT path, #50)
        self._derive_battery_state()

        # Riemann sum: integrate power → energy
        self._integrate_energy(parsed)
        # Flush state to disk periodically (non-blocking)
        await self.hass.async_add_executor_job(self._energy_integrator.flush)

        self._snapshot = DeviceSnapshot(
            data=dict(self._device_data),
            captured_at=time.monotonic(),
            source=source,
            key_count=len(self._device_data),
        )
        return dict(self._device_data)

