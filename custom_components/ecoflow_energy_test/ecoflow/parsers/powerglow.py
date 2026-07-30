"""Read-only PowerGlow quota and report parser."""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Iterable
from typing import Any

from . import _safe_float

_FIELD_MAP: dict[str, str] = {
    "heatingPower": "heating_power_w",
    "hrPwr": "heating_power_w",
    "targetPower": "target_power_w",
    "temp": "water_temperature_c",
    "targetTemp": "target_temperature_c",
    "fromPv": "power_from_pv_w",
    "fromGrid": "power_from_grid_w",
    "fromBat": "power_from_battery_w",
    "waterTankVolume": "water_tank_volume_l",
    "selfcheckPercent": "self_check_pct",
    "mode": "mode_raw",
    "runFlag": "run_flag_raw",
    "runStat": "run_state_raw",
    "errorCode": "error_code_raw",
}

_REPORT_SUFFIXES = (
    "JTS1_HEATING_ROD_PARAM_REPORT",
    "JTS1_HEATING_ROD_ENERGY_STREAM_REPORT",
)

_PARAM_REPORT_SUFFIX = _REPORT_SUFFIXES[0]
_ENERGY_REPORT_SUFFIX = _REPORT_SUFFIXES[1]
_PARAM_FIELDS = (
    "heatingPower",
    "targetPower",
    "temp",
    "targetTemp",
    "waterTankVolume",
    "selfcheckPercent",
    "mode",
    "runFlag",
    "runStat",
    "errorCode",
)
_ENERGY_FIELDS = ("hrPwr", "fromPv", "fromGrid", "fromBat")
_SERIAL_RE = re.compile(r"^[A-Z0-9]{12,32}$")


def parse_powerglow_quota(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize direct HF33 HTTP quota or a known report envelope.

    The developer API commonly uses flat dotted ``ems_heating_rod.*`` keys or
    an exact nested ``ems_heating_rod`` object.  Generic keys such as ``temp``,
    ``mode``, and ``errorCode`` must not be read from the rest of the device
    response because they also occur in unrelated PowerOcean reports.
    """
    result: dict[str, Any] = {}
    for source in _iter_dicts(data):
        nested = source.get("ems_heating_rod")
        if isinstance(nested, dict):
            result.update(_parse_fields(nested, _FIELD_MAP))

        dotted: dict[str, Any] = {}
        for raw_key in _FIELD_MAP:
            dotted_key = f"ems_heating_rod.{raw_key}"
            if dotted_key in source:
                dotted[raw_key] = source[dotted_key]
        result.update(_parse_fields(dotted, _FIELD_MAP))

    # Some app MQTT quota replies contain the named reports directly.  This
    # helper only visits those exact reports, never arbitrary response fields.
    result.update(parse_powerglow_detail_response(data))
    return result


def parse_powerglow_detail_response(
    response: dict[str, Any],
    device_sn: str | None = None,
) -> dict[str, Any]:
    """Parse only known reports belonging to ``device_sn``.

    The parameter report is a flat dictionary.  The energy report contains an
    ``hrEnergyStream`` list and can carry several heating rods, so every list
    item is matched independently through ``hrSn``.  Parameter values are
    merged first and energy-stream values second; therefore ``hrPwr`` is the
    preferred live source for the shared ``heating_power_w`` key.
    """
    parameter_reports: list[dict[str, Any]] = []
    energy_reports: list[dict[str, Any]] = []
    for kind, report in _iter_powerglow_reports(response):
        if kind == "parameter":
            parameter_reports.append(report)
        else:
            energy_reports.append(report)

    result: dict[str, Any] = {}
    for report in parameter_reports:
        if _belongs_to_device(report, device_sn):
            result.update(_parse_fields(report, _PARAM_FIELDS))

    for report in energy_reports:
        stream = report.get("hrEnergyStream")
        entries = stream if isinstance(stream, list) else [report]
        for item in entries:
            if isinstance(item, dict) and _belongs_to_device(item, device_sn):
                result.update(_parse_fields(item, _ENERGY_FIELDS))

    return result


def extract_powerglow_reports(response: dict[str, Any]) -> dict[str, Any]:
    """Return only known heating-rod reports for privacy-safe diagnostics."""
    reports: dict[str, Any] = {}
    counts: dict[str, int] = {}
    for kind, report in _iter_powerglow_reports(response):
        key = _PARAM_REPORT_SUFFIX if kind == "parameter" else _ENERGY_REPORT_SUFFIX
        counts[key] = counts.get(key, 0) + 1
        output_key = key if counts[key] == 1 else f"{key}#{counts[key]}"
        reports[output_key] = report
    return reports


def _iter_powerglow_reports(value: Any):
    """Yield exact known reports without treating the whole detail as telemetry."""
    for container in _iter_dicts(value):
        for key, report in container.items():
            if not isinstance(key, str) or not isinstance(report, dict):
                continue
            if key.endswith(_PARAM_REPORT_SUFFIX):
                yield "parameter", report
            elif key.endswith(_ENERGY_REPORT_SUFFIX):
                yield "energy", report


def _parse_fields(
    source: dict[str, Any],
    field_names: Iterable[str],
) -> dict[str, Any]:
    """Convert selected report fields to transport-neutral numeric keys."""
    result: dict[str, Any] = {}
    for raw_key in field_names:
        sensor_key = _FIELD_MAP[raw_key]
        numeric = _safe_float(source.get(raw_key))
        if numeric is not None:
            result[sensor_key] = numeric
    return result


def _belongs_to_device(report: dict[str, Any], device_sn: str | None) -> bool:
    """Return whether a report has the requested, verifiable heating-rod SN."""
    if device_sn is None:
        return True
    report_sn = _decode_report_sn(report.get("hrSn"))
    return bool(report_sn) and report_sn.upper() == device_sn.upper()


def _iter_dicts(value: Any):
    """Yield every dictionary in a decoded JSON response, outermost first."""
    if not isinstance(value, dict):
        return
    yield value
    for nested in value.values():
        if isinstance(nested, dict):
            yield from _iter_dicts(nested)
        elif isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict):
                    yield from _iter_dicts(item)


def _decode_report_sn(value: Any) -> str:
    """Return a plain or base64-encoded report serial as text."""
    if not isinstance(value, str) or not value:
        return ""
    plain = value.strip()
    if _SERIAL_RE.fullmatch(plain.upper()):
        return plain
    try:
        decoded = base64.b64decode(plain, validate=True).decode("utf-8").strip()
    except (binascii.Error, UnicodeDecodeError):
        return plain
    if _SERIAL_RE.fullmatch(decoded.upper()):
        return decoded
    return plain
