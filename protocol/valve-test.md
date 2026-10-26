# Dedicated valve-test protocol

This protocol runs at 115200 baud, UTF-8 newline-delimited JSON, `v: 1` and
positive integer request IDs. It never authorizes production control. The
separate `esp32-valve-test` firmware identifies itself as `membrane-valve-test`,
with mode `valve_test`, `simulation: false`, `hardware_verified: false`,
`protocol_version: 1`, `valve_count: 7`, a firmware version, profile ID and boolean
`valve_profile_verified`. A locked factory profile still answers HELLO.

| Request | Fields and behavior |
| --- | --- |
| `hello` | Disarms the current session before returning identity. |
| `heartbeat` | Renews a one-second lease; does not arm or change outputs. |
| `stop` | Disarms and clears any pulse; accepted even while locked. |
| `valve_arm` | Matching `profile_id` and exact booleans `wiring_checked`, `pump_isolated`, `test_area_ready`, all true. Requires reviewed valid compiled profile and fresh heartbeat. |
| `valve_pulse` | Integer `valve` 1-7, integer `duration_ms` 100-2000. Requires armed session and fresh heartbeat. No overlap, queued pulse or extension. |

Successful replies are `type: hello` or `type: ack`, `ok: true`, with matching
request ID. Rejections are `type: error`, `ok: false` and an explanation. Startup
noise/ROM text is tolerated only during bounded desktop identity discovery.

`type: valve_test_status` includes `uptime_ms`, `state` (`locked`, `disarmed`,
`ready`, `pulsing`, `fault`), `profile_id`, `valve_profile_verified`,
`outputs_enabled`, `active_valve` (0 or 1-7), `remaining_ms`, `fault` and the
simulation/production-verification flags. Sensor fields are null. Output status
describes commanded state; there is no measured contact or valve-position feedback.

The desktop requires matching acknowledgements, fresh status and heartbeat
acknowledgements. It observes a pulse's active and completed state before
allowing another. Profile changes, unexpected output state, stale status,
timeouts or board restart close the connection and withdraw the heartbeat.
Stop/disconnect/close removes session attestations. Neither sensor availability
nor a GUI confirmation changes the compiled profile's review status.

No recipe, manual experiment, pump, raw-bit, arbitrary-mask or runtime profile
write command is supported. Bare relay bench firmware and this identity are
rejected by the normal experiment controller. See [setup and operation](../docs/valve-test.md).
