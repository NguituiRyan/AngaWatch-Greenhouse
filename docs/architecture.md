# Architecture

AngaWatch closes a loop from a sensor in a Kenyan greenhouse to an action in the
field. This document describes the four layers, the data flow through them, and
the scheduled (Celery beat) jobs that keep the loop turning.

See also: [`data-model.md`](data-model.md) (entities + tenancy),
[`risk-models.md`](risk-models.md) (the decision layer), [`api.md`](api.md)
(REST surface), and [`../NOTES.md`](../NOTES.md) (implemented-vs-stubbed status).

---

## The four layers

```
┌──────────────┐   LoRa    ┌──────────────┐   MQTT    ┌──────────────────────────┐
│ 1. SENSE     │ ───868MHz▶│ 2. CONNECT   │ ────────▶ │ 3. DECIDE                │
│ ESP32 node   │           │ field gateway│           │ ingestion → risk engine  │
│ + instant    │           │ store&forward│           │ + weather fusion         │
│ threshold    │           │ (SQLite WAL) │           │                          │
│ relay/buzzer │           └──────────────┘           └────────────┬─────────────┘
└──────────────┘                                                   │
       ▲                                                           ▼
       │ actuator command (MQTT)                       ┌────────────────────────┐
       └───────────────────────────────────────────── │ 4. ACT                 │
                                                       │ alerting (SMS/WhatsApp/│
                                                       │ USSD/console)          │
                                                       │ control (vents/valves) │
                                                       │ billing (M-Pesa gate)  │
                                                       └────────────────────────┘
```

### 1. Sense — `firmware/`

A solar ESP32 + SX1276/RFM95 LoRa node wakes on an RTC timer, reads the sensor bus
(air temp/RH, leaf wetness, soil moisture/temp, RS485 NPK, PPFD, pheromone trap,
battery), runs **instant microclimate threshold rules locally** (so a relay/buzzer
fires even with no backhaul), encodes a telemetry JSON packet, transmits it over
868 MHz LoRa, and sleeps. The on-device thresholds in
`firmware/include/thresholds.h` mirror the backend `microclimate` model.

### 2. Connect — `gateway/` + `backend/app/ingestion/`

The **field gateway** subscribes to the local broker (`farm/#`), writes every
message to a durable WAL SQLite buffer *before* forwarding, and batch-republishes
to the cloud broker with exponential backoff — offline-first, at-least-once.

The **ingestion consumer** (`app.ingestion.consumer`) subscribes to the cloud
broker on `farm/+/+/telemetry`, parses the topic into `(org_id, device_uid)`,
validates the payload against `TelemetryIn`, and calls
`persist_reading(session, org_id, telem)`. The writer is sync, idempotent
(composite PK `(device_id, time)`), strictly tenant-scoped, and denormalises
`org_id` + `greenhouse_id` onto each `readings` row.

### 3. Decide — `backend/app/risk_engine/` + `backend/app/weather/`

`evaluate_greenhouse(session, greenhouse_id, now)` is the single sync entry point.
For one greenhouse it loads a ~48 h reading window, the active `CropCycle` (crop +
stage + NPK targets), the recent `WeatherForecast`, and the applicable
`RiskModelConfig` rows; resolves each model's params (precedence **greenhouse >
org > global**); runs every enabled model; persists a `RiskAssessment` per result;
and for actionable (MEDIUM+) results upserts a deduplicated `Alert` plus a
bilingual `Recommendation`. The five models are pure functions of
`(readings, params, forecast)` — see [`risk-models.md`](risk-models.md).

### 4. Act — `alerting/`, `control/`, `billing/`

- **Alerting:** `dispatch_alert` resolves recipients (active org users), honours
  per-user channel + language + quiet-hours (org timezone), sends via the channel
  registry (console always available; SMS/WhatsApp fall back to console when
  unconfigured), and records every attempt in `alert.dispatch_log`.
- **Control:** `enqueue_command` queues a `ControlCommand`; `execute_command`
  resolves the driver (mock acks immediately; `mqtt` relay publishes), enforces
  safety interlocks, and updates actuator state. `evaluate_rules` (Wave 1
  scaffold) will auto-fire enabled `AutomationRule`s.
- **Billing:** `org_has_feature` gates premium predictive features; M-Pesa STK
  push (mock when unconfigured) drives subscription activation.

---

## End-to-end data flow

A single late-blight event, traced through the stack:

1. **Node** reads `RH 95%`, `temp 18 °C` at dusk; its local rules see no *instant*
   trip (blight is a windowed model), so it just transmits the packet over LoRa.
2. **Gateway** buffers and forwards the packet to the cloud broker, preserving the
   topic `farm/{org_id}/GH1-NODE-01/telemetry`.
3. **Ingestion consumer** validates and `persist_reading()`s the row into the
   `readings` hypertable, denormalising `org_id`/`greenhouse_id`.
4. **Celery beat** fires `evaluate_all_greenhouses` (every `RISK_EVAL_INTERVAL_MINUTES`).
   The task calls `evaluate_greenhouse(GH-1)`.
5. **Risk engine** loads the trailing wet-hour run, fuses the overnight forecast,
   crosses the HIGH threshold (≥10 wet hours), persists a `RiskAssessment`, and
   upserts a `PENDING` `Alert` + bilingual `Recommendation` ("ventilate now / apply
   preventive fungicide tonight" / "pitisha hewa sasa…").
6. **Celery beat** fires `dispatch_pending_alerts` (every 60 s). The dispatcher
   sends the Swahili text by SMS to the farmer, English by WhatsApp to the
   agronomist (or console fallback offline), and logs each attempt.
7. **(Wave 1)** an enabled `AutomationRule` enqueues an `open` command for
   `GH1-VENT-01`; `execute_command` applies it via the mock/MQTT driver and flips
   the actuator state — the loop is closed.

The same flow handles *Tuta*, heat, nutrient and leak events; only the model and
the recommendation text differ.

---

## Celery beat schedule

Defined in `app.workers.celery_app` (`celery_app.conf.beat_schedule`). The worker
autodiscovers task modules under `app.risk_engine`, `app.weather`, `app.alerting`,
`app.control`, `app.billing`. Timezone is `Africa/Nairobi` with `enable_utc=True`;
`task_acks_late=True` and `worker_max_tasks_per_child=200`.

| Beat entry | Task | Schedule | Status |
| ---------- | ---- | -------- | ------ |
| `evaluate-risk` | `app.risk_engine.tasks.evaluate_all_greenhouses` | `RISK_EVAL_INTERVAL_MINUTES × 60` s (default 600 s) | Implemented. |
| `poll-weather` | `app.weather.tasks.poll_all_farms` | `WEATHER_POLL_INTERVAL_MINUTES × 60` s (default 1800 s) | Implemented — `app.weather.service.poll_farm` fetches current + forecast from the configured `WeatherProvider` (`mock`/`openweather`/`tomorrowio`) and stores `WeatherObservation` + `WeatherForecast` rows the late-blight model fuses. |
| `dispatch-alerts` | `app.alerting.tasks.dispatch_pending_alerts` | `60` s | Implemented. |
| `reconcile-payments` | `app.billing.tasks.reconcile_pending_payments` | `300` s | Implemented. |

> Beat references tasks by dotted name and `autodiscover_tasks` tolerates a
> missing `tasks` module at import time, so the stack always starts cleanly even
> while a domain's task module is being added.

---

## Process topology (Docker Compose)

| Service | Command | Role |
| ------- | ------- | ---- |
| `postgres` | TimescaleDB image | Relational store + `readings` hypertable. |
| `redis` | redis:7 | Celery broker (db 1) / result backend (db 2) / cache (db 0). |
| `mosquitto` | eclipse-mosquitto:2 | MQTT broker for telemetry + actuator commands. |
| `migrate` | `alembic upgrade head` | One-shot schema + hypertable creation. |
| `backend` | `uvicorn app.main:app` | The REST API (`/api/v1`, `/docs`). |
| `ingestion` | `python -m app.ingestion.consumer` | MQTT → `readings`. |
| `worker` | `celery … worker` | Executes the beat tasks. |
| `beat` | `celery … beat` | Fires the schedule above. |
| `web` | `npm run dev` | Vite dashboard (scaffolded). |
| `simulator` | `python -m simulator.run` (profile `sim`) | Virtual nodes for offline demos. |
