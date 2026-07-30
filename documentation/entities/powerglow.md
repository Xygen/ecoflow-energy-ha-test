# PowerGlow (read-only)

PowerGlow devices are detected by the product name `PowerGlow` or the confirmed
9 kW serial-number prefix `HF33`.

The integration exposes heating and target power, water and target temperature,
the PV/grid/battery power split, tank volume, self-check progress, and disabled
by default raw diagnostic values for mode, run flag, run state, and error code.
`heatingPower` (HTTP/parameter report) and `hrPwr` (energy-stream report) are two
transport names for the same `heating_power_w` entity. Heating energy is derived
from that power using the integration's persistent Riemann-sum integrator.

In Enhanced Mode the known heating-rod reports are read from the associated
PowerOcean parent approximately every 30 seconds. Reports are assigned to the
HF33 device through `hrSn`; when both reports are present, `hrPwr` wins and
`heatingPower` remains the fallback. Direct HF33 protobuf frames are recorded
only in masked diagnostics until their field layout has been verified.

No PowerGlow controls are provided because the write protocol is not confirmed.
