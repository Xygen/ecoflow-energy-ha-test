"""Shared fixtures for EcoFlow Energy Test tests.

The ecoflow/ sub-package (core library) has no HA dependencies and can be
tested standalone.  We add its parent to sys.path so tests can import
``ecoflow_energy_test.ecoflow.*`` — but the HA integration modules
(coordinator, config_flow, sensor, …) are NOT importable here because
they require homeassistant.

For the ecoflow sub-package we also register it directly so that
``from ecoflow_energy_test.ecoflow.X import Y`` works even though the
parent ``ecoflow_energy_test.__init__`` would fail (HA imports).
"""

import importlib
import sys
import types
from enum import Enum
from pathlib import Path

_CC = Path(__file__).resolve().parent.parent / "custom_components"

# Put custom_components/ on sys.path
if str(_CC) not in sys.path:
    sys.path.insert(0, str(_CC))

# Register the ecoflow_energy_test package as a namespace so that importing
# ecoflow_energy_test.ecoflow.* works without triggering ecoflow_energy_test/__init__.py
# (which imports homeassistant).
_PKG = "ecoflow_energy_test"
if _PKG not in sys.modules:
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(_CC / _PKG)]
    pkg.__package__ = _PKG
    sys.modules[_PKG] = pkg

# A small subset of the root unit tests inspects entity definition dataclasses
# without needing a Home Assistant runtime. CI installs Home Assistant and
# never uses this fallback; lightweight parser-only environments only need the
# Platform enum imported by const.py.
try:
    importlib.import_module("homeassistant.const")
except ModuleNotFoundError:
    ha_pkg = types.ModuleType("homeassistant")
    ha_pkg.__path__ = []
    ha_const = types.ModuleType("homeassistant.const")

    class Platform(str, Enum):
        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"
        SWITCH = "switch"
        NUMBER = "number"
        SELECT = "select"

    ha_const.Platform = Platform
    sys.modules["homeassistant"] = ha_pkg
    sys.modules["homeassistant.const"] = ha_const
