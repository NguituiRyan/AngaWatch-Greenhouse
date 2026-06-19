# Hardware integration — wiring the dashboard to a real (or emulated) ESP node

This is the operator guide for closing the **full MQTT loop** between an AngaWatch
greenhouse node and the dashboard: telemetry up, actuator commands down, and the
device state ack that confirms what the relay actually did.

The backend half of this loop is **already built and live-verified** over a real
MQTT broker (see [`scripts/verify_loop.py`](../scripts/verify_loop.py)). This doc
shows how to run it end-to-end on a machine **without Docker**, using the bundled
dev broker + ESP emulator, or against a real flashed ESP32.

See also: [`architecture.md`](architecture.md) (the four layers),
[`CONTRACT.md`](CONTRACT.md#mqtt-control-loop-command-down--state-ack-up) (the wire contract),
[`firmware.md`](firmware.md) (the node firmware), and
[`../NOTES.md`](../NOTES.md) (implemented-vs-stubbed status).

---

## 1. The closed loop

```
  ┌─────────────────┐
  │   DASHBOARD      │  operator clicks "Open vent" on GH1-VENT-01
  │  (web/, REST)    │
  └────────┬─────────┘
           │  POST /actuators/{id}/command   {command:"open"}
           ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  BACKEND                                                     │
  │  control.service.enqueue_command → execute_command          │
  │  → driver_registry["mqtt"] = MqttRelayDriver                │
  └───────┬──────────────────────────────────────────▲──────────┘
          │ (A) command DOWN                          │ (C) state ack UP
          │ farm/{org}/{node}/command                 │ farm/{org}/{node}/state
          ▼                                           │
  ┌─────────────────────────────────────────────────────────────┐
  │  MQTT BROKER   (dev_broker.py amqtt :1883  /  Mosquitto)     │
  └───────▲──────────────────────────────────────────┬──────────┘
          │ (B) telemetry UP                          │
          │ farm/{org}/{node}/telemetry               │ command DOWN
          │                                           ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  ESP NODE  (real ESP32 firmware/  OR  scripts/esp_emulator)  │
  │  • samples sensors → publishes telemetry every interval     │
  │  • subscribes to .../command → flips the relay              │
  │  • publishes .../state ack {state, ok} after the relay flips│
  └─────────────────────────────────────────────────────────────┘

  Ingestion consumer (python -m app.ingestion.consumer) subscribes to BOTH
  farm/+/+/telemetry  and  farm/+/+/state, persisting readings (B) and turning
  each state ack (C) into the confirmed ActuatorDevice.state + an ACKED command.
```

Three messages make the loop:

| Leg | Direction | Topic | Who publishes | Who consumes |
| --- | --------- | ----- | ------------- | ------------ |
| **B** telemetry up | node → cloud | `farm/{org_id}/{device_uid}/telemetry` | ESP node / emulator | `app.ingestion.consumer` → `persist_reading` |
| **A** command down | cloud → node | `farm/{org_id}/{device_uid}/command` | `MqttRelayDriver` (backend) | ESP node / emulator |
| **C** state ack up | node → cloud | `farm/{org_id}/{device_uid}/state` | ESP node / emulator | `app.ingestion.consumer` → `handle_state_message` |

The dashboard sets an **optimistic** state the moment the command publishes
(`acked=False`); the real `ActuatorDevice.state` is only confirmed — and the
`ControlCommand` flipped to `ACKED` — when leg **C** lands. That is the whole
point of the ack: the UI reflects what the hardware actually did, not what we
asked it to do.

> **`device_uid` in the command/state topics is the relay-bearing NODE**
> (`GH1-NODE-01`), not the actuator. The actuator (`GH1-VENT-01`) is carried in
> the payload's `actuator_uid`. One node can drive several actuators.

---

## 2. The MQTT contract (verified — do not change topic shapes)

All three topics follow `farm/{org_id}/{device_uid}/{suffix}`. `org_id` is the
seeded organization UUID; `device_uid` matches a seeded `Device.device_uid`. The
ingestion consumer subscribes with wildcards (`farm/+/+/telemetry`,
`farm/+/+/state`) and parses `(org_id, device_uid)` back out of the topic.

### 2.1 Telemetry UP — `farm/{org_id}/{device_uid}/telemetry`

Payload = the `TelemetryIn` JSON
([`backend/app/schemas/telemetry.py`](../backend/app/schemas/telemetry.py)).
`ts` accepts epoch seconds, epoch millis, or ISO-8601 (normalised to aware UTC).
`?` marks optional fields; everything else is range-validated and rejected if
physically impossible.

```json
{
  "device_id": "GH1-NODE-01",
  "ts": 1718800000,
  "air_temp_c": 24.1,
  "rh_pct": 64.0,
  "leaf_wetness": 8.0,
  "soil_moisture_pct": 42.0,
  "soil_temp_c": 22.0,
  "ppfd": 600.0,
  "co2_ppm": 450.0,
  "npk_n_ppm": 165,
  "npk_p_ppm": 78,
  "npk_k_ppm": 215,
  "water_flow_l_total": 0.0,
  "water_flow_l_per_min": 0.0,
  "pheromone_count": 3,
  "battery_v": 3.9,
  "rssi": -67
}
```

Fields: `device_id`, `ts`, `air_temp_c`, `rh_pct`, `leaf_wetness`,
`soil_moisture_pct`, `soil_temp_c`, `ppfd`, `co2_ppm?`, `npk_n_ppm?`,
`npk_p_ppm?`, `npk_k_ppm?`, `water_flow_l_total?`, `water_flow_l_per_min?`,
`pheromone_count`, `battery_v`, `rssi`.

> If the firmware omits `device_id`, the consumer backfills it from the topic's
> `device_uid`, so a topic-only firmware still validates.

### 2.2 Command DOWN — `farm/{org_id}/{device_uid}/command`

`device_uid` = the relay-bearing **node**. Published by
[`MqttRelayDriver`](../backend/app/control/drivers/mqtt_relay.py) at QoS 1.

```json
{
  "command_id": "8f1c2e34-...",
  "actuator_uid": "GH1-VENT-01",
  "actuator_type": "vent",
  "command": "open",
  "params": {},
  "ts": "2026-06-19T08:00:00+00:00"
}
```

`command` is one of `open` | `close` | `on` | `off`. The firmware maps the verb to
a relay state (`open→open`, `close→closed`, `on→on`, `off→off`) and **must echo
`command_id` + `actuator_uid` back in the state ack** so the backend can correlate.

### 2.3 State / ack UP — `farm/{org_id}/{device_uid}/state`

Published by the firmware **after** the relay physically flips. Consumed by
[`handle_state_message`](../backend/app/control/ingest.py).

```json
{
  "command_id": "8f1c2e34-...",
  "actuator_uid": "GH1-VENT-01",
  "state": "open",
  "ok": true,
  "ts": "2026-06-19T08:00:01+00:00"
}
```

- `state` ∈ `open` | `closed` | `on` | `off` → sets `ActuatorDevice.state` and
  `last_state_change`, marks the actuator online.
- `ok` (default `true`): `true` → command `ACKED`; `false` → command `FAILED`
  (with an optional `error` string).
- `command_id` correlates to the exact `ControlCommand`; if omitted, the backend
  falls back to the most recent un-acked command for that actuator.

`handle_state_message` is idempotent and defensive — an unknown actuator or
malformed payload is logged and skipped, never fatal to the consumer.

---

## 3. Run the loop WITHOUT Docker (this machine)

Four terminals. Use the backend virtualenv:
`backend\.venv\Scripts\python.exe`. The scripts live at the **repo root**
under `scripts/`.

### Terminal 1 — MQTT broker (amqtt, no Docker/Mosquitto)

```powershell
backend\.venv\Scripts\python.exe scripts\dev_broker.py
# [broker] amqtt listening on 0.0.0.0:1883 (anonymous)
```

> Anonymous, no TLS — dev only. The real deployment uses Mosquitto from
> `docker-compose.yml`.

### Terminal 2 — backend API (pointed at the local broker)

```powershell
$env:MQTT_HOST = "localhost"
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000
```

(First run only: bring up a database, `alembic upgrade head`, then
`backend\.venv\Scripts\python.exe -m app.seed.seed` — see §5.)

### Terminal 3 — ingestion consumer (telemetry + state ack)

```powershell
$env:MQTT_HOST = "localhost"
cd backend
.\.venv\Scripts\python.exe -m app.ingestion.consumer
# mqtt.connected ... telemetry=farm/+/+/telemetry state=farm/+/+/state
```

This one process subscribes to **both** `farm/+/+/telemetry` (→ `readings`) and
`farm/+/+/state` (→ confirmed actuator state + `ACKED` command).

### Terminal 4 — the node: real ESP **or** emulator

**Option A — no hardware (emulator):**

```powershell
backend\.venv\Scripts\python.exe scripts\esp_emulator.py --org-id <ORG_ID> --uid GH1-NODE-01
# optional: --host localhost --port 1883 --interval 5 --scenario normal|blight|heat
```

The emulator publishes contract-shaped telemetry every interval, subscribes to
`.../command`, flips a virtual vent relay on a command, and publishes the
`.../state` ack — exactly mirroring the real firmware over the wire.

**Option B — real ESP32:** flash the WiFi firmware under `firmware/` (env
`esp32-wifi`, WiFi + broker credentials in `firmware/include/secrets.h`),
pointing `MQTT_HOST` at this machine's LAN IP. See [`firmware.md`](firmware.md)
and `firmware/README.md`. The node uses the **same** topics/payloads as the
emulator, so the backend cannot tell the two apart.

With all four running you should see telemetry rows arrive and — once control is
enabled (§4) — a dashboard "open vent" round-trip to the node and back.

---

## 4. Enabling hardware control (mqtt driver)

By default newly-seeded actuators use the **`mock`** driver
(`CONTROL_DEFAULT_DRIVER=mock`): commands ack instantly in-process and never touch
the broker. To drive a real (or emulated) relay you must switch the actuator to
the **`mqtt`** driver. Two ways:

**Option 1 — re-seed with the mqtt default (cleanest):**

```powershell
$env:CONTROL_DEFAULT_DRIVER = "mqtt"
backend\.venv\Scripts\python.exe -m app.seed.seed
```

The seed stamps `config.driver` from `settings.control_default_driver` onto the
vent actuator (see `_create_vent` in `backend/app/seed/seed.py`). The seed is
idempotent on the org slug, so on an **already-seeded** org this is a no-op for
the existing rows — use Option 2 to flip an existing actuator.

**Option 2 — flip the existing actuator's driver:** set the seeded vent's
`config.driver` to `"mqtt"` (via a DB update or admin path). `execute_command`
resolves the driver per-actuator from `config["driver"]`, so the change takes
effect on the next command with no restart.

### Graceful mqtt → mock fallback (no broker)

`MqttRelayDriver` is **fail-soft**: a connect/publish failure does not raise — it
returns `CommandResult(ok=False, ...)` and logs `mqtt_driver_publish_failed`, so
the service layer can fall back to the mock driver and the whole stack still runs
offline. This means:

- **Broker up + node listening** → command published, ack arrives over `.../state`,
  command flips `ACKED` (the real closed loop).
- **No broker** → the publish fails softly; the actuator still reflects the
  optimistic state and the stack keeps running. You simply do not get a hardware
  ack until a broker + node are present.

The `mock` driver is **always** registered and acks immediately, so the demo and
the tests never depend on a broker being up.

---

## 5. Getting the ORG_ID (and matching device_uid)

`org_id` in every topic is the seeded organization's **UUID** (not the slug
`demo-coop`). Print it from the seed:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.seed.seed
```

The summary prints the value you need:

```
  Organization : Demo Cooperative (demo-coop)  [already present (idempotent skip)]
  Org ID       : 1b9d6bcd-bbfd-4b2d-9b5d-ab8dfbbd4bed   <-- this is <ORG_ID>
  Device       : GH1-NODE-01
  Vent         : GH1-VENT-01 (state=closed)
```

Pass that UUID as `--org-id` to the emulator and to `verify_loop.py`. The
**`device_uid` must match a seeded `Device`** (`GH1-NODE-01`) and the actuator
uid a seeded `ActuatorDevice` (`GH1-VENT-01`) — otherwise `persist_reading`
(unknown device) and `handle_state_message` (`control.state.unknown_actuator`)
drop the message. These uids are the single source of truth in
[`backend/app/seed/constants.py`](../backend/app/seed/constants.py).

---

## 6. The loop verifier — `scripts/verify_loop.py`

`verify_loop.py` asserts the full loop over a **real broker**, end to end. Run it
**from `backend/`** with the venv so the `app.*` imports resolve, with a broker +
emulator already running (§3):

```powershell
cd backend
.\.venv\Scripts\python.exe ..\scripts\verify_loop.py <ORG_ID>
```

It does three things and prints a numbered result for each:

1. **telemetry up** — waits for a contract-valid `TelemetryIn` on `.../telemetry`.
2. **command down** — calls the **real backend** `MqttRelayDriver.apply(...)` to
   publish an `open` command to `GH1-NODE-01`.
3. **ack up** — waits for the device's `.../state` ack and asserts
   `state == "open"`, `ok is true`, and the `command_id` round-tripped.

```
[verify] 1/3 telemetry OK  air_temp=24.1C rh=64.0%
[verify] 2/3 command published  farm/<ORG>/GH1-NODE-01/command  cmd=8f1c2e34
[verify] 3/3 device ACK OK  vent -> open  cmd=8f1c2e34
[verify] PASS - full MQTT closed loop verified (telemetry up, command down, ack up)
```

**PASS** (exit 0) means all three legs of the loop work against a live broker:
the node is publishing valid telemetry, the backend driver can command it, and
the device's ack flows back to confirm the relay state. Any **FAIL** (exit 1)
prints which leg broke — see troubleshooting below.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
| ------- | ------------ | --- |
| **No telemetry** — consumer/dashboard show nothing | broker not running, or `MQTT_HOST` mismatch | Start `scripts/dev_broker.py`; set `MQTT_HOST=localhost` on the consumer **and** emulator; confirm `mqtt.connected` in the consumer log. |
| No telemetry, consumer logs `mqtt.invalid_payload` | payload out of range / wrong shape | Compare against §2.1; check sensor ranges (`air_temp_c -40..80`, `rh_pct 0..100`, etc.). |
| No telemetry, consumer logs `mqtt.bad_topic` | wrong topic shape or non-UUID `org_id` | Topic must be `farm/{org_id}/{device_uid}/telemetry`; `org_id` must be the seeded **UUID** from §5, not `demo-coop`. |
| Telemetry arrives but **device not in dashboard** | `device_uid` not seeded | `persist_reading` drops unknown devices — the uid must match a seeded `Device` (`GH1-NODE-01`). |
| **Command not acted** — relay never flips | actuator still on `mock` driver | Enable mqtt control (§4): re-seed with `CONTROL_DEFAULT_DRIVER=mqtt` or flip `config.driver` to `"mqtt"`. |
| Command not acted — no `.../command` reaches the node | node subscribed to the wrong topic / wrong `org_id` | Command goes to the **node** uid (`GH1-NODE-01`), not the actuator; verify the node subscribes to `farm/{org_id}/{node_uid}/command`. |
| Command not acted — driver logs `mqtt_driver_publish_failed` | broker down | The driver fails soft to mock; start the broker to get a real round-trip (§4). |
| **Ack not received** — command stuck `SENT`, state stays optimistic | firmware did not publish `.../state` | After flipping the relay the node MUST publish `{command_id, actuator_uid, state, ok}` to `farm/{org_id}/{node_uid}/state`. Mirror `scripts/esp_emulator.py`. |
| Ack received but command not `ACKED` | `command_id` / `actuator_uid` mismatch | Echo the **exact** `command_id` and `actuator_uid` from the command; otherwise the backend logs `control.state.unknown_actuator` or cannot correlate the command. |
| `verify_loop.py` FAILs at 1/3 | no telemetry within 20 s | Start the emulator (§3 Option A); confirm broker + `--org-id` match. |
| `verify_loop.py` FAILs at 3/3 | no ack within 20 s | Emulator/firmware not acking; check the node subscribed to `.../command` and is publishing `.../state`. |
| `ModuleNotFoundError: app` running `verify_loop.py` | wrong cwd / interpreter | Run **from `backend/`** with `backend\.venv\Scripts\python.exe`. |
