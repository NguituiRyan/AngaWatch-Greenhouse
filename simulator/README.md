# AngaWatch Device Simulator

A standalone package that emulates greenhouse sensor nodes publishing telemetry
over MQTT. It exists so the whole AngaWatch stack (ingestion → risk engine →
alerting) can be demoed and tested **offline**, with deterministic,
agronomically realistic scenarios.

It does **not** import the backend `app` package — it only depends on
`paho-mqtt` and `pydantic`. The telemetry field names mirror
`app.schemas.telemetry.TelemetryIn` exactly, but the contract is duplicated here
on purpose so the simulator runs with zero backend dependencies.

## Layout

```
simulator/
├── pyproject.toml          # package metadata + deps (paho-mqtt, pydantic)
├── README.md               # this file
├── Dockerfile              # python -m simulator.run
├── simulator/              # the package
│   ├── config.py           # SimulatorConfig.from_env()
│   ├── node.py             # VirtualNode — diurnal baseline physics
│   ├── publisher.py        # MqttPublisher (paho v2) + NullPublisher
│   ├── run.py              # Simulation core + main() loop / CLI
│   └── scenarios/          # one module per scenario
└── tests/                  # pytest suite
```

## The telemetry payload

Each node publishes JSON to `farm/{org_id}/{device_uid}/telemetry` with these
fields (matching the contract):

`device_id, ts, air_temp_c, rh_pct, leaf_wetness, soil_moisture_pct,
soil_temp_c, ppfd, co2_ppm, npk_n_ppm, npk_p_ppm, npk_k_ppm,
water_flow_l_total, water_flow_l_per_min, pheromone_count, battery_v, rssi`

The `VirtualNode` produces a healthy diurnal baseline (cool humid nights, warm
dry afternoons, a PPFD bell over the day, a morning irrigation pulse, slow
battery/NPK/soil drift). Curves are phased against **Africa/Nairobi local
time** so dusk/overnight risk windows line up with the backend risk engine.

## Scenarios

Selected via `SIM_SCENARIO` (env) or `--scenario` (CLI). Each reshapes the
baseline reading given the local hour-of-day to drive one risk condition.

| Scenario             | What it drives                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------ |
| `normal`             | Healthy greenhouse — pass-through baseline; no risk should fire.                                  |
| `blight_dusk`        | **Late blight.** Pins `rh_pct ≥ 90` with `air_temp_c` in 16–26 °C and free leaf wetness from ~17:00 to ~03:00 local — a sustained ~10 h wet window straddling midnight, so the blight model reaches its HIGH (≥10 wet-hours) condition. |
| `heat_stress`        | **Over-temperature.** Pushes the midday peak (11:00–16:00) above 35 °C with low RH → "vent now".  |
| `pest_surge`         | **Tuta absoluta.** Ramps `pheromone_count` past the trap threshold (30) and warms the days for degree-day accumulation. |
| `nutrient_depletion` | Drains `npk_*` below crop-stage targets and keeps depleting → fertigation recommendation.        |
| `leak`               | Steady unscheduled `water_flow_l_per_min` outside the irrigation window → leak (HIGH).            |
| `offline`            | Drops all messages during a local-time gap (09:00–12:00) → device-offline / stale-data path.      |

## Usage

Install deps (into the backend venv, which already has paho-mqtt + pydantic):

```powershell
backend\.venv\Scripts\python.exe -m pip install paho-mqtt pydantic
```

Run from the `simulator/` directory so `simulator` resolves as a package:

```powershell
cd simulator
# One tick per node, printed only, no broker needed:
..\backend\.venv\Scripts\python.exe -m simulator.run --dry-run --once

# Drive the blight scenario, 20 ticks, accelerated clock, against a broker:
$env:SIM_SCENARIO="blight_dusk"; $env:SIM_TIME_ACCEL="3600"
..\backend\.venv\Scripts\python.exe -m simulator.run --count 20
```

### CLI flags

- `--once` — emit exactly one tick per node and exit.
- `--count N` — emit N ticks per node and exit (no inter-tick sleep; fast for demos/tests).
- `--scenario S` — override `SIM_SCENARIO`.
- `--dry-run` — never connect to MQTT; print only (uses the in-memory `NullPublisher`).
- `--start ISO8601` — set the simulated start time (UTC). Default: now.

### Environment variables

| Variable             | Default       | Meaning                                              |
| -------------------- | ------------- | ---------------------------------------------------- |
| `MQTT_HOST`          | `localhost`   | Broker host.                                         |
| `MQTT_PORT`          | `1883`        | Broker port.                                         |
| `MQTT_USERNAME`      | _(none)_      | Optional broker auth.                                |
| `MQTT_PASSWORD`      | _(none)_      | Optional broker auth.                                |
| `SIM_ORG_ID`         | `demo-coop`   | Tenant segment of the MQTT topic.                    |
| `SIM_NODE_COUNT`     | `1`           | Number of virtual nodes.                             |
| `SIM_SCENARIO`       | `normal`      | One of the scenarios above.                          |
| `SIM_INTERVAL_SECONDS` | `5`         | Wall-clock seconds between ticks (infinite runs).    |
| `SIM_TIME_ACCEL`     | `1.0`         | Simulated-clock speed-up (e.g. `3600` = 1 s ⇒ 1 h).  |
| `SIM_DEVICE_UID_PREFIX` | `GH1-NODE-01` | Device uid; node 0 uses the bare prefix (`GH1-NODE-01`). |

### Time acceleration

Wall-clock sleep between ticks is always `SIM_INTERVAL_SECONDS`, but the
*simulated* clock advances by `interval × time_accel` per tick. With
`SIM_TIME_ACCEL=3600` a single real second represents one simulated hour, so the
10-hour `blight_dusk` window forms in ~10 real seconds — handy for demos where
you want the risk engine to fire quickly.

## Tests

```powershell
backend\.venv\Scripts\python.exe -m pytest simulator\tests -q
```

The suite asserts every scenario yields in-range, schema-shaped dicts and that
`blight_dusk` actually reaches the wet-hour condition (`rh ≥ 90` with
`16 ≤ air_temp ≤ 26`) sustained for ~10 hours.
