# Relay board test protocol

Separate firmware target: `esp32-relay-bench`. UART remains 115200 8N1,
newline-delimited strict JSON using v1 envelopes and request IDs. This device
identifies as `membrane-relay-bench`, not the experiment controller. It reports
`simulation: false`, `hardware_verified: false`, `relay_count: 16` and protocol 1.

All commands return a matching `ack` with `ok: true`, or `error` with `ok: false`.
`hello` returns `hello`. Only `hello`, `heartbeat`, `stop`, `bench_probe`,
`bench_confirm` and `bench_pulse` are supported. Recipe, start and manual
experiment commands are rejected.

| Command | Fields |
| --- | --- |
| `bench_probe` | `baseline_word`: integer 0 or 65535; `duration_ms`: integer 100-2000; `loads_disconnected`: true |
| `bench_confirm` | `probe_id`: ID of the latest completed probe; matching `baseline_word`; `loads_disconnected`: true; `all_relays_off`: true |
| `bench_pulse` | `bit`: integer 0-15; `duration_ms`: integer 100-2000 |

A probe can energize multiple bare relays. Confirmation is an operator's
observation of that completed probe, not electronic contact feedback. A pulse
toggles one bit relative to the confirmed rest word. It does not assign a valve
number or automatically verify a physical profile. Active tests cannot be
replaced or prolonged by repeated commands.

`bench_status` reports uptime, state (`disarmed`, `probing`, `ready`, `pulsing`,
`fault`), `outputs_enabled`, `baseline_word`, `baseline_confirmed`, `probe_id`,
`probe_completed`, `pulse_bit`, `remaining_ms`, mode flags and fault. Sensor values
are null. These are commanded output states, not measured relay positions.

Startup and STOP disable OE before latching a rest word. A pulse expiry disables
OE and restores the rest word. A one-second heartbeat lease applies to the armed
session, including idle confirmation. STOP, HELLO/new session, reset and lease
expiry invalidate the observation. No previous pulse or confirmation resumes.

Candidate board wiring is data GPIO14, clock GPIO13, latch GPIO12, OE GPIO5
(active low). GPIO4/SRCLR, sensors, I2C and pump interfaces are untouched. Physical
OE bias and reset behavior still need measurement; high-impedance outputs are
not measured proof that each relay is de-energized.
