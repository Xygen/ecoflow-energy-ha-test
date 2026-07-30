<div align="center">

# EcoFlow Energy Test

**Real-time solar, battery, grid & home power monitoring for Home Assistant.**
Energy Dashboard ready. Two modes: official API or real-time app connection.

</div>

## What you get

- **Up to 200 sensors per device** — power, energy, battery packs, temperature, diagnostics
- **Energy Dashboard ready** — local Riemann-sum kWh with gap detection
- **Real-time updates** — Enhanced Mode pushes supported device data every 2-4 seconds; PowerGlow uses ~30-second read-only report polling
- **Full PowerOcean control** — Backup Reserve, Solar Surplus Threshold, Work Mode, all verified against the official EcoFlow app
- **Delta switches & numbers** — AC/DC output, charge speed, backup reserve, screen settings
- **Smart Plug** — power monitoring, on/off switch, max power limit
- **Auto-discovery** — picks up every device bound to your EcoFlow account
- **PowerGlow HF33** — read-only heating, temperature, source-power, status, and energy sensors; no control commands

## Supported devices

| Device | Sensors | Controls |
|:---|:---:|:---|
| **PowerOcean** (Home Battery) | 202 | 2 numbers, 1 select (Enhanced only) |
| **PowerGlow** (HF33 Heating Rod) | 14 | Read-only |
| **Delta 2 Max** (Portable Power) | 94 | 7 switches, 8 numbers |
| **Smart Plug** | 11 | 1 switch, 2 numbers |

Other Delta-series devices (Delta Pro, Delta 2, etc.) typically work automatically with the Delta sensor set.

## Two modes

**Standard Mode** (recommended for stability)

Uses the official EcoFlow IoT Developer API. Apply for free API keys at [developer.ecoflow.com](https://developer.ecoflow.com). HTTP polling at ~30 seconds, plus MQTT push for Delta and Smart Plug. PowerOcean is read-only in this mode.

**Enhanced Mode** (recommended for control + speed)

Connects with your EcoFlow email and password. No Developer API keys needed. Real-time WSS MQTT updates and full PowerOcean controls (Backup Reserve, Solar Surplus, Work Mode). This is an unofficial, community-driven protocol that may change without notice.

## Install

This test fork is not in the HACS default store. Install the supplied ZIP
manually, or publish the complete fork in a GitHub repository and add it under
**HACS > Custom repositories** as an **Integration**. Restart Home Assistant,
then use **Settings > Devices & Services > Add Integration > EcoFlow Energy
Test**.

For full documentation, configuration details, automation examples, and
troubleshooting, see the repository README.
