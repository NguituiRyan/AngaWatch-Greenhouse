# AngaWatch Greenhouse — Hackathon Demo Runbook

> **The story in one line:** AngaWatch catches a tomato crop disease *before* it
> spreads, tells the farmer in their own language, and acts on it — closing the
> loop from sensor to alert to a vent that opens itself.

This runbook gives you three ways to show that loop, from "just works in 30
seconds" to "the full IoT stack with a live broker". Pick the one that fits the
room.

| Path | What it shows | Needs |
| ---- | ------------- | ----- |
| **A. `make demo`** (recommended) | The whole scripted story, narrated, in containers. | Docker Desktop |
| **B. Full-stack simulator** | Real telemetry over MQTT → ingestion → risk engine → alert, on the dashboard. | Docker Desktop |
| **C. `--direct` fallback** | The scripted story in-process, no broker, no workers. | Python venv only |

The cast of every path is the **same seeded demo data** (one source of truth in
`backend/app/seed/constants.py`):

- Cooperative **`demo-coop`**, farm near **Nakuru** (`lat=-0.303, lon=36.080`).
- Greenhouse **GH-1**, sensor node **GH1-NODE-01**, vent **GH1-VENT-01**.
- A tomato crop **planted ~45 days ago, in the `flowering` stage**.
- Three users (password **`password123`**):
  - `admin@demo-coop.ke` — coop_admin (English, WhatsApp)
  - `agronomist@demo-coop.ke` — agronomist (English, WhatsApp)
  - `farmer@demo-coop.ke` — farmer, phone `+254700000001` (**Swahili**, SMS)

---

## Prerequisites

- **Docker Desktop** running (paths A and B). Compose v2 (`docker compose ...`).
- For path C only: the backend virtualenv at
  `backend\.venv\Scripts\python.exe` (already provisioned).
- Copy the env file once: `cp .env.example .env` (the `make` targets do this for
  you via the `env` target). All integrations are **mock-first** — no M-Pesa,
  SMS, WhatsApp or weather accounts are required; unconfigured channels fall back
  to the console.

> **Windows without `make`:** every `make <target>` has a twin in
> `./make.ps1 <target>` (PowerShell). Or run the underlying `docker compose`
> commands shown below directly.

---

## Path A — `make demo` (the 30-second pitch)

One command brings up the stack, seeds the demo data, and runs the narrated
script:

```bash
make demo
```

That target is exactly:

```bash
docker compose up -d                                  # postgres + redis + mqtt + backend + workers + web
docker compose exec backend python -m app.seed.seed   # idempotent: org, farm, GH-1, tomato cycle, 36h history
docker compose exec backend python -m app.seed.demo   # the scripted story
```

You'll watch eight clearly-headed stages scroll by:

1. **SEED** — the `demo-coop` cooperative and its greenhouse are ensured (idempotent).
2. **ALL CLEAR** — the healthy baseline: no actionable risk. This is what a
   free-tier farmer sees every day.
3. **BLIGHT DUSK** — a wet, cool evening is injected (~12 h of `rh ≥ 90 %` with
   air temp in the 16–26 °C late-blight band). Leaves stay wet overnight —
   exactly how *Phytophthora infestans* spreads.
4. **DETECT** — the predictive risk engine fires a **HIGH late-blight**
   assessment and writes a recommendation in **English *and* Swahili**.
5. **ALERT** — the alert is dispatched to every org user *in their language*.
   The console channel is always on; SMS/WhatsApp fall back to it when
   unconfigured. The Swahili farmer gets the Swahili message.
6. **UNLOCK** — a subscription is paid via a **mock M-Pesa STK push** + success
   callback; the subscription advances **trial → active**, keeping the
   predictive features unlocked past the trial.
7. **ACT** — a `ControlCommand` opens **GH1-VENT-01** (mock driver acks
   immediately; the actuator state becomes `open`). Opening the vents exchanges
   the saturated air.
8. **RESOLVE** — post-break dry readings are injected and the engine is re-run;
   late-blight risk falls back to **NONE**. The crop is saved.

When it's done, stop everything with `make down` (or `make clean` to also drop
the database volume).

---

## Path B — the full-stack simulator (the "it's real" demo)

This is the impressive version: real telemetry flows over MQTT, the ingestion
consumer writes it, Celery beat periodically runs the risk engine, and you watch
the risk climb to HIGH **on the dashboard**.

### 1. Bring the stack up and seed

```bash
docker compose up -d
docker compose exec backend python -m app.seed.seed
```

The stack includes `postgres` (TimescaleDB), `redis`, `mosquitto` (MQTT),
`backend` (API at <http://localhost:8000>), `ingestion` (the MQTT consumer),
`worker` + `beat` (Celery), and `web` (the dashboard at
<http://localhost:5173>). Migrations run automatically via the `migrate`
service.

### 2. Run the simulator in the marquee scenario

The simulator publishes to `farm/{org_id}/{device_uid}/telemetry`, agreeing with
the seed constants (`demo-coop` / `GH1-NODE-01`). Drive the **`blight_dusk`**
scenario, which pins `rh ≥ 90 %` and `16 ≤ air_temp ≤ 26 °C` from ~17:00 to
~03:00 local — a sustained ~10 h wet window that reaches the blight model's HIGH
(≥ 10 wet-hours) condition:

```bash
# In .env, set the scenario (and optionally accelerate the simulated clock):
#   SIM_SCENARIO=blight_dusk
#   SIM_TIME_ACCEL=3600        # 1 real second => 1 simulated hour; the window forms in ~10 s
docker compose --profile sim up simulator      # or: make simulate
```

`SIM_TIME_ACCEL=3600` is the demo trick: the 10-hour wet window forms in ~10
real seconds, so the risk engine (which `beat` triggers on its interval) flips
GH-1 to HIGH while you're still talking.

### 3. What to watch on the dashboard (<http://localhost:5173>)

Log in as `farmer@demo-coop.ke` / `password123`, open **GH-1**, and narrate:

- **Live readings** — relative humidity climbs to ~95 % and air temp settles into
  the high teens. The leaf-wetness tile lights up.
- **Risk panel** — *Late blight* moves `none → medium → **HIGH**` as the wet
  hours accumulate. (History beyond 24 h and the predictive view are gated by
  `require_feature(...)`, unlocked by the subscription — see below.)
- **Recommendation** — the bilingual action card: *"Ventilate now and apply a
  preventive fungicide tonight."* / *"Pitisha hewa sasa na nyunyizia dawa..."*.
- **Alerts** — a HIGH late-blight alert appears with status `sent`; the dispatch
  log shows one entry per recipient (the farmer's is in Swahili). Watch the
  `worker`/`backend` logs (`make logs`) to see the `alert.console.send` events.
- **Subscription** — `POST /api/v1/billing/subscribe` triggers a (mock) STK
  push; posting the mock callback to `POST /api/v1/billing/mpesa/callback`
  flips the subscription `trial → active` and unlocks the predictive/history
  features.
- **Control** — fire `POST /api/v1/actuators/{GH1-VENT-01}/command` with
  `{"command": "open"}`; the vent state becomes `open`. Switch the simulator to
  `SIM_SCENARIO=normal` (the humidity break) and watch the risk fall again.

> Tip: keep `make logs` open in a second terminal — the structured
> `risk.eval.done`, `alerting.dispatch`, and `control_command_acked` events tell
> the same story the dashboard does.

---

## Path C — the `--direct` fallback (no broker, no Docker)

If Docker is unavailable or the broker is being temperamental, the **same
scripted story** runs entirely in-process against the database, with zero
brokers or workers. This is the resilient backup for a live stage.

Against the dockerized Postgres (recommended), from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m app.seed.seed
.\.venv\Scripts\python.exe -m app.seed.demo            # --direct is the default mode
```

`python -m app.seed.demo` injects the blight window, runs
`app.risk_engine.engine.evaluate_greenhouse`, shows the HIGH assessment and the
EN/SW recommendation, dispatches the alert via
`app.alerting.dispatcher.dispatch_alert`, simulates the M-Pesa
subscribe-and-callback so predictive features unlock, enqueues + executes the
"open vent" command, and re-runs the engine to show the risk resolving — the
full eight-stage narration, identical to Path A.

It is **resilient by design**: if the database is unreachable it prints a clear
message telling you to start the stack first, and the async billing/control
stages degrade gracefully if their session can't connect.

### Quick offline smoke (SQLite, no services at all)

You can even run it with no Postgres by pointing the database at a local SQLite
file and creating the schema first:

```powershell
$env:DATABASE_URL      = "sqlite+aiosqlite:///./demo.db"
$env:DATABASE_URL_SYNC = "sqlite:///./demo.db"
.\.venv\Scripts\python.exe -c "from app.db.base import Base; from app.db.session import sync_engine; import app.db.models; Base.metadata.create_all(sync_engine)"
.\.venv\Scripts\python.exe -m app.seed.seed
.\.venv\Scripts\python.exe -m app.seed.demo
```

---

## Verifying the demo (CI-style)

The detect → alert core of the demo is covered by a test that builds a sync
SQLite engine, seeds, injects the blight window, evaluates, and asserts a HIGH
late-blight `RiskAssessment` and an `Alert` row are produced:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests\test_demo_flow.py -q
```

---

## Reset between runs

- `make down` — stop the stack (keeps the database).
- `make clean` — stop the stack **and drop the volume** (fresh DB next time).
- The seed is **idempotent**: re-running `python -m app.seed.seed` on an existing
  `demo-coop` org is a safe no-op that just reprints the summary.

---

## Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `[demo] The database is not reachable` | `docker compose up -d`, then `alembic upgrade head` (the `migrate` service does this automatically) and re-run the seed. |
| Risk never reaches HIGH in Path B | Confirm `SIM_SCENARIO=blight_dusk` and give it enough (accelerated) time; the model needs **≥ 10 consecutive wet-hours**. Bump `SIM_TIME_ACCEL`. |
| No alert delivered | Expected offline: SMS/WhatsApp aren't configured, so delivery falls back to the **console** — check `make logs` for `alert.console.send`. |
| Want it in Swahili | Log in as `farmer@demo-coop.ke`; that user's `preferred_language` is `sw`, so its alert text and dashboard copy are Swahili. |
