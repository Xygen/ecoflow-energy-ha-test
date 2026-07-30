"""PowerGlow Home Assistant entity definition tests."""

from custom_components.ecoflow_energy_test.const import (
    DEVICE_TYPE_POWERGLOW,
    POWERGLOW_POWER_TO_ENERGY,
    POWERGLOW_SENSORS,
)
from custom_components.ecoflow_energy_test.sensor import _get_sensor_defs


def test_powerglow_sensor_setup() -> None:
    assert _get_sensor_defs(DEVICE_TYPE_POWERGLOW) is POWERGLOW_SENSORS
    heating = next(item for item in POWERGLOW_SENSORS if item.key == "heating_power_w")
    assert heating.unit == "W"
    assert heating.device_class == "power"
    assert heating.state_class == "measurement"
    raw_codes = {
        "mode_raw", "run_flag_raw", "run_state_raw", "error_code_raw"
    }
    assert all(
        item.state_class is None
        for item in POWERGLOW_SENSORS
        if item.key in raw_codes
    )
    assert POWERGLOW_POWER_TO_ENERGY == {
        "heating_power_w": "heating_energy_kwh"
    }
