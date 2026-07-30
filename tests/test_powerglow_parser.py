"""PowerGlow classification and parser tests."""

import base64
import json
from pathlib import Path

from ecoflow_energy_test.ecoflow.const import DEVICE_TYPE_POWERGLOW, get_device_type
from ecoflow_energy_test.ecoflow.parsers.powerglow import (
    extract_powerglow_reports,
    parse_powerglow_detail_response,
    parse_powerglow_quota,
)


def test_powerglow_classification() -> None:
    assert get_device_type("PowerGlow", "") == DEVICE_TYPE_POWERGLOW
    assert get_device_type("", "HF33ABCD1234") == DEVICE_TYPE_POWERGLOW


def test_flat_quota() -> None:
    parsed = parse_powerglow_quota({
        "ems_heating_rod.heatingPower": 4500,
        "ems_heating_rod.targetPower": "5000",
        "ems_heating_rod.temp": 48.5,
    })
    assert parsed == {
        "heating_power_w": 4500.0,
        "target_power_w": 5000.0,
        "water_temperature_c": 48.5,
    }


def test_nested_quota() -> None:
    parsed = parse_powerglow_quota({"ems_heating_rod": {
        "heatingPower": 3000,
        "targetTemp": 60,
        "waterTankVolume": 300,
    }})
    assert parsed["heating_power_w"] == 3000.0
    assert parsed["target_temperature_c"] == 60.0
    assert parsed["water_tank_volume_l"] == 300.0


def test_hrpwr_and_heating_power_normalize_to_same_key() -> None:
    parameter = {"JTS1_HEATING_ROD_PARAM_REPORT": {"heatingPower": 3123}}
    energy = {"JTS1_HEATING_ROD_ENERGY_STREAM_REPORT": {
        "hrEnergyStream": [{"hrPwr": 3123}]
    }}
    assert parse_powerglow_quota(parameter) == {"heating_power_w": 3123.0}
    assert parse_powerglow_quota(energy) == {"heating_power_w": 3123.0}


def test_known_report_fields_and_invalid_values() -> None:
    parsed = parse_powerglow_quota({
        "errorCode": 999,
        "JTS1_HEATING_ROD_PARAM_REPORT": {
            "selfcheckPercent": 100, "mode": 2, "runFlag": 1,
            "runStat": 3, "errorCode": 0, "heatingPower": "invalid",
        },
        "JTS1_HEATING_ROD_ENERGY_STREAM_REPORT": {
            "hrEnergyStream": [{
                "fromPv": 1000, "fromGrid": 2000, "fromBat": 500,
            }]
        },
    })
    assert "heating_power_w" not in parsed
    assert parsed["power_from_pv_w"] == 1000.0
    assert parsed["error_code_raw"] == 0.0


def test_consumer_detail_reports_and_hrpwr_precedence() -> None:
    response = {
        "code": "0",
        "data": {
            "quota": {
                "JTS1_HEATING_ROD_PARAM_REPORT": {
                    "hrSn": "HF33000000000001",
                    "heatingPower": 2998,
                    "targetPower": 3500,
                    "temp": 51.25,
                    "targetTemp": 60,
                    "waterTankVolume": 300,
                    "selfcheckPercent": 100,
                    "mode": 2,
                    "runFlag": 1,
                    "runStat": 3,
                    "errorCode": 0,
                },
                "JTS1_HEATING_ROD_ENERGY_STREAM_REPORT": {
                    "hrEnergyStream": [{
                        "hrSn": "HF33000000000001",
                        "hrPwr": 3001,
                        "fromPv": 2000,
                        "fromGrid": 1001,
                        "fromBat": 0,
                    }],
                },
            }
        },
    }

    parsed = parse_powerglow_detail_response(response, "HF33000000000001")

    assert parsed["heating_power_w"] == 3001.0
    assert parsed["target_power_w"] == 3500.0
    assert parsed["water_temperature_c"] == 51.25
    assert parsed["power_from_pv_w"] == 2000.0
    assert parsed["power_from_grid_w"] == 1001.0
    assert parsed["power_from_battery_w"] == 0.0


def test_parallel_consumer_detail_and_compact_report_capture() -> None:
    response = {
        "data": {
            "parallel": {
                "HJ3100001": {
                    "JTS1_HEATING_ROD_PARAM_REPORT": {
                        "hrSn": "HF33000000000001", "heatingPower": 900,
                    }
                }
            },
            "unrelated": {"account": "must not be captured"},
        }
    }
    assert parse_powerglow_detail_response(
        response, "HF33000000000001"
    )["heating_power_w"] == 900.0
    assert extract_powerglow_reports(response) == {
        "JTS1_HEATING_ROD_PARAM_REPORT": {
            "hrSn": "HF33000000000001", "heatingPower": 900,
        }
    }


def test_consumer_detail_hrsn_association() -> None:
    response = {"data": {"quota": {
        "JTS1_HEATING_ROD_PARAM_REPORT": {
            "hrSn": "HF33000000000001", "heatingPower": 1200,
        }
    }}}
    assert parse_powerglow_detail_response(
        response, "HF33000000000001"
    )["heating_power_w"] == 1200.0
    assert parse_powerglow_detail_response(response, "HF33999999999999") == {}


def test_energy_stream_filters_each_heating_rod_by_serial() -> None:
    response = {"data": {"quota": {
        "JTS1_HEATING_ROD_PARAM_REPORT": {
            "hrSn": "HF33000000000002", "heatingPower": 9999,
        },
        "JTS1_HEATING_ROD_ENERGY_STREAM_REPORT": {
            "hrEnergyStream": [
                {
                    "hrSn": "HF33000000000002", "hrPwr": 8999,
                    "fromPv": 8000, "fromGrid": 999, "fromBat": 0,
                },
                {
                    "hrSn": "HF33000000000001", "hrPwr": 3001,
                    "fromPv": 2000, "fromGrid": 1001, "fromBat": 0,
                },
            ]
        },
    }}}

    parsed = parse_powerglow_detail_response(response, "HF33000000000001")

    assert parsed["heating_power_w"] == 3001.0
    assert parsed["power_from_pv_w"] == 2000.0
    assert "target_power_w" not in parsed


def test_base64_report_serial_is_matched_safely() -> None:
    serial = "HF33000000000001"
    encoded = base64.b64encode(serial.encode()).decode()
    response = {"data": {"quota": {
        "JTS1_HEATING_ROD_PARAM_REPORT": {
            "hrSn": encoded, "heatingPower": 1800,
        }
    }}}

    assert parse_powerglow_detail_response(
        response, serial
    )["heating_power_w"] == 1800.0
    assert parse_powerglow_detail_response(response, "HF33000000000002") == {}


def test_unrelated_generic_fields_never_leak_from_device_detail() -> None:
    response = {"data": {
        "errorCode": 777,
        "otherReport": {"temp": 99, "mode": 9, "heatingPower": 8888},
        "quota": {
            "JTS1_HEATING_ROD_PARAM_REPORT": {
                "hrSn": "HF33000000000001", "heatingPower": 1200,
            }
        },
    }}

    parsed = parse_powerglow_detail_response(response, "HF33000000000001")

    assert parsed == {"heating_power_w": 1200.0}


def test_powerglow_translation_completeness() -> None:
    expected = {
        "heating_power_w",
        "heating_energy_kwh",
        "target_power_w",
        "water_temperature_c",
        "target_temperature_c",
        "power_from_pv_w",
        "power_from_grid_w",
        "power_from_battery_w",
        "water_tank_volume_l",
        "self_check_pct",
        "mode_raw",
        "run_flag_raw",
        "run_state_raw",
        "error_code_raw",
    }
    root = Path("custom_components/ecoflow_energy_test")
    for relative in ("strings.json", "translations/en.json", "translations/de.json"):
        content = json.loads((root / relative).read_text(encoding="utf-8"))
        translated = content["entity"]["sensor"]
        assert expected <= set(translated), f"Missing PowerGlow translations in {relative}"
        assert all(translated[key].get("name") for key in expected)
