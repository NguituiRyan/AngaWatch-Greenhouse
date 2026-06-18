# AngaWatch — Implementation Notes

This is the honest, per-module status of the platform: what is fully implemented,
what is a deliberate scaffold, and where the agronomy is a calibratable placeholder
awaiting field data. It complements [`README.md`](README.md) (the pitch + setup)
and [`docs/CONTRACT.md`](docs/CONTRACT.md) (the seam spec).

---

## Implemented vs. stubbed — by module

Legend: **Done** = fully implemented + tested; **Partial** = core path done, edges
deferred; **Scaffold** = data model and/or a safe no-op in place, logic TODO;
**Model-only** = ORM tables exist, no service/API yet.

### Ingestion

| Component | Status | Notes |
| --------- | ------ | ----- |
| `app.schemas.telemetry.TelemetryIn` | Done | Wire contract; epoch-s/ms/ISO `ts` normalised to aware UTC; physical-range validation. |
| `app.ingestion.writer.persist_reading` | Done | Sync, idempotent (composite PK `(device_id, time)` → `IntegrityError` caught on PG **and** SQLite), denormalises `org_id`/`greenhouse_id`, refreshes device health, strict tenant check (drops on org mismatch / unknown device). |
| `app.ingestion.consumer.main` | Done | paho-mqtt v2 loop, auto-reconnect, topic parse `farm/{org_id}/{device_uid}/telemetry`, per-message isolation. Runnable as `python -m app.ingestion.consumer`. |

### Risk engine (5 models)

| Model | Status | Notes |
| ----- | ------ | ----- |
| `late_blight` (`models/blight.py`) | Done | Trailing consecutive wet-hour accumulator + overnight forecast fusion. **Thresholds are Kenya placeholders.** |
| `tuta_absoluta` (`models/tuta.py`) | Done | Degree-day integration above base temp + pheromone-trap escalation. **`generation_dd=208` is an explicit calibration placeholder.** |
| `microclimate` (`models/microclimate.py`) | Done | Latest-reading temp/RH/soil guardrails; mirrors the on-firmware instant rules. |
| `nutrient` (`models/nutrient.py`) | Done | Latest NPK vs crop-stage targets from `Crop.npk_targets[stage]`. |
| `water` (`models/water.py`) | Done | Soil + flow fusion: irrigate vs leak detection, plus per-cycle water-use rollup in `details`. |
| `engine.evaluate_greenhouse` | Done | Loads ~48 h window + active cycle + forecast + configs; param precedence greenhouse > org > global; persists assessment; upserts dedup'd alert + bilingual recommendation within `cooldown_hours`. |
| `defaults.seed_risk_configs` | Done | Idempotent seeding of `RiskModelConfig` from each model's `default_params`. |
| `tasks.evaluate_all_greenhouses` | Done | Celery task fan-out over all greenhouses. |

### Alerting (channels)

| Channel / piece | Status | Notes |
| --------------- | ------ | ----- |
| `dispatcher.dispatch_alert` / `dispatch_pending` | Done | Recipients = active org users; per-user channel + language; quiet-hours in org tz; dedup/escalation; per-attempt `dispatch_log`. |
| Console adapter | Done | Always registered; the universal fallback. |
| SMS (Africa's Talking) | Partial | Real httpx client; **falls back to console when `AT_API_KEY` is unset** (`is_configured()` gate). Live path untested without an AT account. |
| WhatsApp (Meta Cloud API) | Partial | Real httpx client; falls back to console when `WHATSAPP_ACCESS_TOKEN`/`PHONE_NUMBER_ID` unset. Inbound webhook verify/echo implemented. |
| USSD (`ussd.handle_ussd`) | Done | Flat pull menu (latest readings / current risk / alerts / subscription balance), bilingual, `CON`/`END` per AT protocol. |
| `tasks.dispatch_pending_alerts` | Done | Celery task, 60 s cadence. |
| Templates (`templates/messages.py`) | Done | Fallback rendering by `action_code` + language when a recommendation has no stored text. |

### Billing

| Component | Status | Notes |
| --------- | ------ | ----- |
| `service.org_has_feature` | Done | Async feature gate over `PLAN_FEATURES`/`PREMIUM_FEATURES`; active/trial subs grant features. |
| `service.initiate_subscription` | Done | Get/create trial sub + pending payment + best-effort STK push. |
| `service.handle_stk_callback` | Done | Reconcile by `checkout_request_id`; on success run the subscription state machine `trial→active` and settle the earliest unpaid installment. |
| `providers.get_payment_provider` | Done | Returns `MpesaProvider` only when both Daraja keys are set, else `MockPaymentProvider` (deterministic, offline). |
| `mpesa.MpesaProvider` | Partial | Real Daraja STK push + callback parsing; **not exercised against the live sandbox** in CI (mock is default). |
| `tasks.reconcile_pending_payments` | Done | Celery task, 300 s cadence. |

### Control

| Component | Status | Notes |
| --------- | ------ | ----- |
| `service.enqueue_command` | Done | Async; persists `QUEUED` `ControlCommand`. |
| `service.execute_command` | Done | Resolves driver, enforces interlocks (`min_cycle_interval_s`), applies, sets `ACKED`/`SENT`/`FAILED`, updates actuator state. |
| `drivers/mock.py` | Done | Always registered; acks immediately and flips `ActuatorDevice.state`. |
| `drivers/mqtt_relay.py` | Partial | Publishes a command to MQTT; degrades to a non-acked `SENT` result when no broker — real relay round-trip/ack untested. |
| `automation.evaluate_rules` | Scaffold | Wave 1. Loads enabled rules, checks `{metric,op,value}` against the latest reading, respects basic interlocks, enqueues `AUTO` commands. **Safe no-op when no rules are enabled.** TODOs: `duration_min` sustained windows, hysteresis, auto-close timers, forecast-fused triggers, in-flight de-dup. |

### Weather

| Component | Status | Notes |
| --------- | ------ | ----- |
| `providers.MockWeatherProvider` | Done | Deterministic Nakuru diurnal climatology (no RNG); overnight window deliberately crosses the blight wet-hour band for forecast fusion. |
| `providers.OpenWeatherProvider` / `TomorrowIoProvider` | Partial | Real httpx clients; only constructed when the API key is set, else mock fallback. Live paths untested without keys. |
| `service.poll_farm` | Done | Async; stores `WeatherObservation` + `WeatherForecast`. |
| `tasks.poll_all_farms` | Done | Celery task. |

### API

| Router | Status | Notes |
| ------ | ------ | ----- |
| `auth` | Done | login / register / me / refresh (JWT). |
| `organizations` | Done | `GET /me`, org patch (super_admin). |
| `farms`, `greenhouses`, `devices` | Done | Full org-scoped CRUD. |
| `readings` | Done | timeseries query, latest, optional `POST /ingest`. |
| `risk` | Done | current per-model; history gated by `dashboard_history` feature. |
| `alerts`, `recommendations` | Done | list/ack; list/override (agronomist/coop_admin). |
| `control` | Done | actuators, manual command, command list. |
| `billing` | Done | subscription, subscribe (STK), Daraja callback (no auth), payments. |
| `weather` | Done | latest obs + forecast per farm. |
| `ussd`, `whatsapp` | Done | AT USSD webhook; Meta verify + inbound. |
| `records` | Partial | spray/harvest/expense list+create wired; per-cycle PHI/cost/yield rollup deferred (TODO → 501). |
| invoicing / marketplace / traceability / financing routers | Not started | Model-only; no router yet. |

### Simulator

| Status | Notes |
| ------ | ----- |
| Done | Standalone package (no `app.*` import). `VirtualNode` diurnal physics + 7 scenarios (`normal`, `blight_dusk`, `heat_stress`, `pest_surge`, `nutrient_depletion`, `leak`, `offline`). MQTT + null publishers; CLI (`--once/--count/--scenario/--dry-run/--start`); tested. |

### Gateway

| Status | Notes |
| ------ | ----- |
| Done | Offline-first store-and-forward MQTT bridge. Durable WAL SQLite buffer (write-before-forward), batch forward with exponential backoff, at-least-once delivery, hourly purge of forwarded rows. No `app.*` dependency; tested. |

### Firmware

| Status | Notes |
| ------ | ----- |
| Reference (not CI-compiled) | ESP32 + SX1276/RFM95 LoRa node (PlatformIO). Deep-sleep read→threshold→JSON→TX cycle; on-device **instant** microclimate rules (`thresholds.h` mirrors the backend microclimate model). OTA stubbed/disabled (LoRa-only nodes). Pin maps + calibration constants are sane placeholders to verify per hardware. |

### Web

| Status | Notes |
| ------ | ----- |
| Done (Wave 0) | React 18 + TypeScript + Vite + Tailwind + TanStack Query + Recharts + react-router. `npm install` + `npm run build` (0 TS errors) + vitest all pass. JWT auth (OAuth2 password) + AuthContext, white-label theming, responsive sidebar/topbar. Implemented pages: Login, Dashboard (risk badges, recent alerts+ack, device health), GreenhouseDetail (live values, temp/RH/soil charts, per-model risk + recommendation, **manual actuator control**, device health), Alerts (filter+ack), Recommendations (agronomist override), Devices, Billing (subscription + M-Pesa STK subscribe). |
| Scaffold | Roadmap nav pages with Wave-tagged "coming soon" previews: Records, Invoicing, Input Marketplace, Market Linkage, Traceability/Export, Financing, Yield Forecasting. |

---

## Key design decisions

1. **Two session styles, one ORM.** The request/API path is async
   (`AsyncSession`, `get_db`); ingestion, the risk engine, alerting and Celery use
   the sync session. Pure models (risk, weather, billing providers) take plain
   dataclasses so they are unit-testable with synthetic data and never import the
   ORM.

2. **Mock-first everywhere.** Every external integration (SMS, WhatsApp, M-Pesa,
   weather) ships a deterministic mock that is selected automatically when
   credentials are absent. The entire stack — and the demo — runs with zero
   external accounts. This is enforced at the factory boundary
   (`build_provider`, `get_payment_provider`, `is_configured()`), not sprinkled
   through business logic.

3. **Idempotency without dialect lock-in.** Readings dedupe on the composite PK
   `(device_id, time)` and catch `IntegrityError` rather than using PG-only
   `ON CONFLICT`, so the exact same code path is exercised by the SQLite tests and
   the Timescale deployment. Alerts dedupe on a `dedup_key` within a per-model
   cooldown.

4. **Calibration lives in data, not code.** Each model's `default_params` document
   and seed the knobs; effective params resolve as
   `{**default_params, **config.params}` with precedence **greenhouse > org >
   global**. Recalibrating a threshold is a `RiskModelConfig` row update, never a
   redeploy.

5. **Multi-tenant isolation is mechanical.** `OrgScopedMixin` puts `org_id` on
   every tenant table; `org_id` is denormalised onto `readings` so window queries
   never join back through `devices`; the API bundles `org_id` into `OrgScope` so
   every handler filters by it. See [`docs/data-model.md`](docs/data-model.md).

6. **Bilingual by construction.** Every recommendation carries `message_en` +
   `message_sw`; the dispatcher and USSD menu render in each user's
   `preferred_language`. Swahili is a first-class output, not an afterthought.

7. **Time discipline.** Rows store aware UTC; dusk/quiet-hours are computed in
   `Africa/Nairobi`. The mock weather + simulator curves are phased to Nairobi
   local time so overnight risk windows line up across the whole pipeline.

8. **Self-registering plugins.** Risk models, alert channels and actuator drivers
   each register via a decorator/registry on import, so adding one is a single new
   file — no central wiring to edit.

---

## Agronomic calibration TODOs

> **All of the following are field-calibratable placeholders.** They produce
> sensible, demonstrable behaviour today, but the numbers must be validated
> against Kenyan highland tomato field data (and ideally per-county / per-variety)
> before any agronomic claim is made. Each lives in `RiskModelConfig.params` and
> can be overridden per greenhouse/org without code changes.

- **Late blight wet-hour rule** (`models/blight.py`): `rh_threshold=90`,
  `temp_min=10`, `temp_max=26`, `med_hours=6`, `high_hours=10`,
  `cooldown_hours=12`, `forecast_lookahead_hours=12`. The consecutive-wet-hour
  model is a defensible approximation of *Phytophthora infestans* pressure but is
  **not** a calibrated Smith-period / BLITECAST-style model — treat the hour
  thresholds as the primary tuning target.
- **Tuta absoluta degree-days** (`models/tuta.py`): `base_temp_c=10.0`,
  **`generation_dd=208`** (the single most important placeholder — published
  estimates for a full *Tuta absoluta* generation vary; confirm for local
  conditions), `trap_threshold=30` pheromone catches, `warn_fraction=0.75`,
  `cooldown_hours=24`.
- **Microclimate guardrails** (`models/microclimate.py`): `temp_high=35`,
  `rh_warn=85`, `soil_min=25`, `soil_critical=15`. These also live in the firmware
  (`firmware/include/thresholds.h`) and **must be kept in sync** if re-tuned.
- **Nutrient tolerances** (`models/nutrient.py`): `deficit_fraction=0.15`,
  `severe_fraction=0.35`. The per-stage NPK *targets* themselves
  (`TOMATO_NPK_TARGETS` in `seed/constants.py`) are Kenya placeholders for the
  `Anna F1` variety.
- **Water/leak fusion** (`models/water.py`): `soil_min=25`, `soil_critical=15`,
  `soil_wet=35`, `flow_active=0.5` L/min. Leak detection assumes an
  `irrigation_scheduled` flag is supplied by the orchestrator (currently defaults
  to `False`); wiring real irrigation schedules is a follow-up.
- **Mock weather climatology** (`weather/providers.py`): the Nakuru diurnal means
  and amplitudes (`_TEMP_MEAN_C=18`, `_RH_MEAN_PCT=78`, etc.) are tuned for demo
  realism, not measured — replace with a real provider in production.

References for all of the above are intentionally left as **placeholders** in
[`docs/risk-models.md`](docs/risk-models.md); fill them in with the specific
extension-service / journal sources used to calibrate each threshold.
