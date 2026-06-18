# AngaWatch Greenhouse

**AngaWatch is a Kenya-first IoT crop-loss-prevention platform.** A solar-powered
sensor node in every greenhouse streams microclimate, soil, water and pest
telemetry to the cloud, where an agronomic risk engine turns raw numbers into
*plain-language, bilingual (English + Swahili)* actions — "ventilate now, late
blight forms tonight" — delivered over SMS, WhatsApp or USSD, and optionally
acted on by closing the loop to a vent that opens itself. The moat is not the
hardware; it is the calibrated agronomy: five risk models (late blight, *Tuta
absoluta*, microclimate, nutrient, water) tuned for Kenyan highland tomato.

## 🌐 Live demo

**[angawatch-greenhouse.vercel.app](https://angawatch-greenhouse.vercel.app)** — the
full dashboard hosted on Vercel in self-contained **demo mode** (baked-in
late-blight scenario, no backend needed). Sign in with `admin@demo-coop.ke` /
`password123` to see GH-1 raise a HIGH blight risk, the bilingual recommendation,
the alert feed, telemetry charts, and manual vent control.

> Demo mode (`VITE_DEMO_MODE=true`) serves captured fixtures through the api
> layer. For live data, run the full stack locally (`docker compose up`) or point
> `VITE_API_BASE_URL` at a hosted backend — see [DEMO.md](DEMO.md).

---

## The 4-layer architecture

AngaWatch is organised as four layers. Each is independently useful; together
they close the sensor-to-action loop.

| Layer | What it does | Where it lives |
| ----- | ------------ | -------------- |
| **1. Sense** | Solar ESP32 + LoRa node reads air temp/RH, leaf wetness, soil moisture/temp, NPK, PPFD, CO₂, water flow, pheromone-trap catches and battery. Runs **instant microclimate threshold rules on-device** so a farmer still gets a local relay/buzzer alert when the network is down. | `firmware/` |
| **2. Connect** | A LoRa field gateway store-and-forwards telemetry over MQTT (offline-first, durable SQLite buffer). The backend ingestion consumer validates every packet against the telemetry contract and writes it idempotently into a TimescaleDB hypertable. | `gateway/`, `backend/app/ingestion/` |
| **3. Decide** | The **agronomic risk engine** — the moat. Five pure models score risk over a recent reading window, fuse the weather forecast, and emit a bilingual recommendation + a deduplicated alert. Calibration knobs live in the database (`RiskModelConfig`), not in code. | `backend/app/risk_engine/`, `backend/app/weather/` |
| **4. Act** | Alerting (SMS/WhatsApp/USSD/console, quiet-hours-aware, language-aware) tells the right human; the control layer enqueues and executes actuator commands (vents/fans/valves) with safety interlocks. Billing (M-Pesa) gates the premium predictive features. | `backend/app/alerting/`, `backend/app/control/`, `backend/app/billing/` |

**The agronomic moat.** Anyone can read a humidity sensor. AngaWatch knows that
≥10 consecutive hours of `RH ≥ 90%` while `10 ≤ temp ≤ 26 °C` is a late-blight
sporulation window, that ~208 degree-days above 10 °C marks a new *Tuta absoluta*
generation, and what NPK a flowering tomato needs in Nakuru. Every threshold is a
**field-calibratable placeholder** stored per greenhouse/org/global, so the
agronomy improves without a redeploy. See [`docs/risk-models.md`](docs/risk-models.md).

---

## Tech stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async API path + sync
  ingestion/Celery path), Pydantic v2 / pydantic-settings, Alembic.
- **Data:** PostgreSQL + **TimescaleDB** (the `readings` hypertable), Redis
  (Celery broker/result/cache).
- **Async work:** Celery worker + beat (risk evaluation, weather polling, alert
  dispatch, payment reconciliation).
- **Messaging:** MQTT (Eclipse Mosquitto) for telemetry and actuator commands;
  `paho-mqtt` clients.
- **Integrations (all mock-first):** Africa's Talking (SMS/USSD), WhatsApp Cloud
  API (Meta), M-Pesa Daraja STK push, OpenWeather / Tomorrow.io.
- **Edge:** ESP32 + SX1276/RFM95 LoRa firmware (PlatformIO); a Raspberry-Pi-class
  store-and-forward gateway.
- **Tooling:** Ruff + Black (line length 100), pytest (+ pytest-asyncio,
  aiosqlite), structlog, Docker Compose.
- **Frontend:** a full multi-tenant dashboard in `web/` — React + TypeScript +
  Vite + Tailwind + TanStack Query + Recharts (JWT auth, live + historical charts,
  per-greenhouse risk, alerts feed, manual actuator control, billing). Builds clean
  (`npm run build`). Roadmap pages (records, invoicing, marketplace, traceability,
  financing, yield forecasting) are scaffolded with "coming soon" previews.

---

## Repository structure

```
Angawatch greenhouse/
├── README.md                 # this file
├── NOTES.md                  # implemented-vs-stubbed status + design decisions
├── DEMO.md                   # the hackathon demo runbook
├── docker-compose.yml        # full local stack (infra + backend + workers + web)
├── Makefile / make.ps1       # task runner (make.ps1 for Windows without make)
├── .env.example              # all configuration (copy to .env)
│
├── docs/
│   ├── CONTRACT.md           # authoritative seam spec for the parallel build
│   ├── architecture.md       # layers, data flow, Celery beat schedule
│   ├── risk-models.md        # the 5 models: inputs, math, thresholds, Kenya notes
│   ├── data-model.md         # entities, multi-tenant rule, Timescale hypertable
│   ├── api.md                # endpoint summary (detail deferred to OpenAPI)
│   └── firmware.md           # firmware pointer/summary
│
├── backend/                  # the Python service
│   ├── app/
│   │   ├── core/             # config, logging, security (foundation)
│   │   ├── db/               # Base, models, session (foundation)
│   │   ├── schemas/          # telemetry wire contract (foundation)
│   │   ├── ingestion/        # MQTT consumer + idempotent reading writer
│   │   ├── risk_engine/      # the 5 models + orchestrator + defaults + task
│   │   ├── weather/          # providers (mock/openweather/tomorrowio) + service
│   │   ├── alerting/         # dispatcher + channel adapters + USSD + templates
│   │   ├── control/          # command service + drivers + automation scaffold
│   │   ├── billing/          # M-Pesa providers + subscription service
│   │   ├── api/              # FastAPI routers + DTO schemas + deps
│   │   ├── seed/             # demo constants + seed + scripted demo
│   │   └── workers/          # Celery app + beat schedule
│   ├── alembic/              # migrations (incl. Timescale hypertable)
│   └── tests/                # pytest suite
│
├── firmware/                 # ESP32 + LoRa sensor-node firmware (PlatformIO)
├── gateway/                  # offline-first MQTT store-and-forward bridge
├── simulator/                # virtual sensor nodes + agronomic scenarios
├── web/                      # React + TS + Vite multi-tenant dashboard
└── infra/                    # Mosquitto + Postgres/Timescale init
```

---

## Prerequisites & setup

- **Docker Desktop** (Compose v2) — the only hard requirement to run the full
  stack.
- **Python 3.12** with the backend virtualenv at
  `backend\.venv\Scripts\python.exe` (already provisioned in this repo) for
  running tests or the in-process demo without Docker.
- **`make` is optional on Windows.** Every `make <target>` has a twin in
  `./make.ps1 <target>` (PowerShell). Examples below show both.

Copy the environment file once (the `env`/`up` targets do this for you):

```bash
cp .env.example .env        # bash
# or, the make way:
make env                    # macOS/Linux
./make.ps1 env              # Windows
```

All integrations are **mock-first**: with no credentials in `.env`, SMS/WhatsApp
fall back to console, payments use a deterministic mock provider, and weather uses
a deterministic Nakuru climatology model. The whole stack runs offline.

---

## Running the stack

Bring up infra (Postgres/Timescale, Redis, Mosquitto), run migrations, then start
the backend API, MQTT ingestion consumer, Celery worker + beat, and the web
container:

```bash
docker compose up -d            # detached
make dev                        # foreground logs (macOS/Linux)
./make.ps1 dev                  # foreground logs (Windows)
```

Seed the demo tenant and run the scripted demo:

```bash
make seed   ;  make demo        # macOS/Linux
./make.ps1 seed ; ./make.ps1 demo   # Windows
```

Run the device simulator (a profile, off by default):

```bash
docker compose --profile sim up simulator
make simulate          # or ./make.ps1 simulate
```

Other handy targets: `migrate`, `down`, `clean` (drops volumes — destroys DB
data), `logs`, `psql`, `lint`, `fmt`, `test`. Run `make help` /
`./make.ps1 help` for the full list.

The compose services are: `postgres`, `redis`, `mosquitto`, `migrate` (one-shot),
`backend` (uvicorn :8000), `ingestion` (MQTT consumer), `worker` (Celery),
`beat` (Celery scheduler), `web` (:5173), and `simulator` (sim profile).

---

## Configuration (`.env`)

The full set is in [`.env.example`](.env.example). The most important variables:

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `ENVIRONMENT` | `local` | `local` / `staging` / `production`. |
| `LOG_LEVEL` / `TZ` | `INFO` / `Africa/Nairobi` | Logging + app timezone (dusk/quiet-hours are computed in `Africa/Nairobi`). |
| `DATABASE_URL` / `DATABASE_URL_SYNC` | `postgresql+asyncpg://…` / `postgresql+psycopg://…` | Async URL (API) and sync URL (Alembic + Celery/ingestion). |
| `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://redis:6379/{0,1,2}` | Cache + Celery broker/backend. |
| `MQTT_HOST` / `MQTT_PORT` | `mosquitto` / `1883` | MQTT broker. |
| `MQTT_TELEMETRY_TOPIC` | `farm/+/+/telemetry` | Subscription filter for the ingestion consumer. |
| `JWT_SECRET` / `JWT_ALGORITHM` | `change-me…` / `HS256` | API auth. Set a real secret in production. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | `60` / `14` | Token lifetimes. |
| `API_CORS_ORIGINS` | `http://localhost:5173,…` | Comma-separated allowed origins. |
| `RISK_EVAL_INTERVAL_MINUTES` | `10` | Beat cadence for risk evaluation. |
| `WEATHER_POLL_INTERVAL_MINUTES` | `30` | Beat cadence for weather polling. |
| `ALERTING_DEFAULT_CHANNEL` | `console` | `console` / `sms` / `whatsapp`. |
| `AT_USERNAME` / `AT_API_KEY` / `AT_SENDER_ID` / `AT_USE_SANDBOX` | `sandbox` / — / `ANGAWATCH` / `true` | Africa's Talking SMS + USSD. Console fallback when `AT_API_KEY` is empty. |
| `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_ACCESS_TOKEN` / `WHATSAPP_API_VERSION` / `WHATSAPP_VERIFY_TOKEN` | — / — / `v21.0` / `angawatch-verify` | WhatsApp Cloud API (Meta). Console fallback when unset. |
| `MPESA_ENVIRONMENT` / `MPESA_CONSUMER_KEY` / `MPESA_CONSUMER_SECRET` / `MPESA_SHORTCODE` / `MPESA_PASSKEY` / `MPESA_CALLBACK_BASE_URL` | `sandbox` / — / — / `174379` / *(sandbox passkey)* / `https://example.ngrok.io` | M-Pesa Daraja STK push. Mock provider when keys are unset. |
| `WEATHER_PROVIDER` / `OPENWEATHER_API_KEY` / `TOMORROWIO_API_KEY` | `mock` / — / — | Weather source. Falls back to the deterministic mock when the key is missing. |
| `SIM_ORG_ID` / `SIM_NODE_COUNT` / `SIM_SCENARIO` / `SIM_INTERVAL_SECONDS` / `SIM_TIME_ACCEL` | — / `3` / `normal` / `5` / `1.0` | Device simulator knobs (see below). |

---

## The device simulator

`simulator/` emulates greenhouse sensor nodes publishing telemetry over MQTT so the
entire pipeline (ingestion → risk engine → alerting) can be demoed and tested
**offline**, with deterministic, agronomically realistic curves. It does not import
the backend `app` package — it depends only on `paho-mqtt` + `pydantic`, and
mirrors the telemetry field names from the contract.

A `VirtualNode` produces a healthy diurnal baseline (cool humid nights, warm dry
afternoons, a PPFD bell over the day, a morning irrigation pulse, slow
battery/NPK/soil drift), phased to **Africa/Nairobi** local time so risk windows
line up with the backend. `SIM_TIME_ACCEL` lets a single real second represent up
to an hour of simulated time, so a 10-hour blight window forms in ~10 seconds.

Scenarios (`SIM_SCENARIO` / `--scenario`):

| Scenario | Drives |
| -------- | ------ |
| `normal` | Healthy greenhouse — no risk should fire. |
| `blight_dusk` | Late blight: a sustained ~10 h wet window (`RH ≥ 90`, `16–26 °C`) straddling midnight → blight model HIGH. |
| `heat_stress` | Over-temperature: midday peak above 35 °C → "vent now". |
| `pest_surge` | *Tuta absoluta*: pheromone catches past the trap threshold + warm days for degree-day accumulation. |
| `nutrient_depletion` | Drains NPK below crop-stage targets → fertigation recommendation. |
| `leak` | Unscheduled steady water flow → leak (HIGH). |
| `offline` | Drops messages during a local-time gap → device-offline / stale-data path. |

See [`simulator/README.md`](simulator/README.md) for CLI flags and usage.

---

## The demo

The full hackathon runbook — three paths from "just works in 30 seconds" to "the
full IoT stack with a live broker" — is in **[`DEMO.md`](DEMO.md)**. The headline:
AngaWatch catches a tomato disease *before* it spreads, tells the farmer in their
own language, and opens a vent to act on it.

---

## Running tests

The backend test suite runs against an in-memory SQLite database (the Timescale
hypertable migration is a no-op off PostgreSQL), so no Docker is needed:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Or via the task runner (Docker): `make test` / `./make.ps1 test`. The simulator and
gateway have their own suites:

```powershell
backend\.venv\Scripts\python.exe -m pytest simulator\tests -q
backend\.venv\Scripts\python.exe -m pytest gateway\tests -q
```

Lint/format: `make lint` / `make fmt` (Ruff + Black, line length 100).

---

## The API

The backend serves an OpenAPI/Swagger UI at **`http://localhost:8000/docs`** (and
ReDoc at `/redoc`). All business endpoints are under the `/api/v1` prefix and use
JWT bearer auth; obtain a token from `POST /api/v1/auth/login` (OAuth2 password
form, `username` = email). A summary table of every endpoint is in
[`docs/api.md`](docs/api.md); the live OpenAPI schema is the source of truth for
request/response shapes.

---

## Roadmap (Wave 0 → Wave 1–3)

**Wave 0 (implemented now):** the full sensor-to-action loop. Telemetry ingestion
into Timescale; all five risk models with weather fusion; bilingual alerting over
console/SM/USSD/WhatsApp with quiet-hours + dedup; manual actuator control with
safety interlocks; M-Pesa subscription billing + feature gating; the REST API for
auth, orgs, farms, greenhouses, devices, readings, risk, alerts, recommendations,
control, billing and weather; the simulator, gateway and firmware.

**Wave 1 (scaffolded):** closed-loop automation (`AutomationRule` data model and a
conservative, TODO-marked `evaluate_rules` engine — a safe no-op until rules are
enabled); farm records (spray/harvest/expense logs are wired as list+create;
per-cycle PHI/cost/yield rollups are deferred); the web dashboard.

**Wave 2–3 (data model only):** invoicing, the input marketplace + market linkage,
solar-dryer post-harvest units, financing/credit-scoring, and GlobalGAP/organic
traceability all have ORM models in place and are awaiting service + API layers.

A precise per-module **implemented-vs-stubbed** matrix, the key design decisions,
and the agronomic calibration TODOs are in **[`NOTES.md`](NOTES.md)**.
