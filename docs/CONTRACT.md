# AngaWatch — Implementation Contract (read this first)

This is the authoritative seam spec for the parallel build. The **foundation is
already built and verified** (33 ORM tables, telemetry schema, interfaces, Celery
app, FastAPI app, Alembic migrations). Your job is to implement one module against
these fixed seams. **Do NOT edit foundation files** (anything under
`backend/app/core`, `backend/app/db`, `backend/app/schemas/telemetry.py`,
`backend/app/api/deps.py`, `backend/app/api/router.py`, `backend/app/main.py`,
`backend/app/workers/celery_app.py`, the `*/base.py` interface files, or
`backend/tests/conftest.py`) unless your task explicitly says so. Only ADD files in
your assigned directory.

## Repo + tooling
- Repo root: `C:\Users\phant\Desktop\Angawatch greenhouse` (Windows; paths use `\`).
- Backend Python package: `backend/app` (import as `app.*`). Python 3.12.
- A ready virtualenv exists: `backend\.venv\Scripts\python.exe`. Run tests with it:
  `cd backend; .\.venv\Scripts\python.exe -m pytest tests\test_yourfile.py -q`.
- Lint/format target: Ruff + Black, line length 100. Full type hints. `from __future__ import annotations` at top of every backend module.
- Logging: `from app.core.logging import get_logger`. Config: `from app.core.config import settings`.

## Conventions
- **SQLAlchemy 2.0**: API/request path is **async** (`AsyncSession`, `app.db.session.get_db`). Celery tasks / ingestion / seed use the **sync** session (`app.db.session.get_sync_session()` / `SyncSessionLocal`). Use `mapped_column`, `Mapped[...]`, `select()`.
- **Pydantic v2** everywhere (`model_config = ConfigDict(...)`, `field_validator`).
- **Multi-tenant isolation is mandatory**: every query against a tenant table filters `org_id`. Models with `OrgScopedMixin` have `org_id`. Denormalized `org_id`/`greenhouse_id` live on `readings`.
- **Time**: store UTC (`datetime.now(UTC)`); compute dusk/quiet-hours in `Africa/Nairobi`. Never use naive datetimes for new rows.
- **Offline/mock-first**: when an integration's credentials are absent in settings, fall back to a console/mock adapter so the whole stack runs with zero external accounts.
- Enums: `app.db.models.common` (UserRole, RiskLevel, RiskModelType, AlertChannelType, AlertStatus, CommandStatus, CommandSource, PlanType, SubscriptionStatus, PaymentStatus, ActuatorType, CropStage, Language, ...). Stored as VARCHAR of `.value`.

## Data model (already defined — import, don't redefine)
`from app.db.models import Organization, User, Farm, Greenhouse, Device, Reading, Crop, CropCycle, RiskModelConfig, RiskAssessment, Alert, Recommendation, ActuatorDevice, AutomationRule, ControlCommand, WeatherObservation, WeatherForecast, FarmRecord, SprayLog, HarvestLog, Expense, Invoice, InputProduct, InputOrder, Buyer, MarketListing, DryerUnit, FinancingProfile, CreditScore, TraceabilityRecord, Subscription, Installment, Payment`
- Hierarchy: Organization → Farm → Greenhouse → Device → Reading. CropCycle is per greenhouse. RiskAssessment/Alert/Recommendation are per greenhouse.
- `Device.device_uid` (unique string) is the id used in the MQTT topic. `Reading` PK = `(device_id, time)`; idempotent inserts.

## Telemetry contract (the wire format)
Nodes publish JSON to MQTT topic **`farm/{org_id}/{device_uid}/telemetry`**. Validate with `from app.schemas.telemetry import TelemetryIn`. Fields:
`device_id` (the device_uid string), `ts` (epoch s/ms or ISO), `air_temp_c`, `rh_pct`, `leaf_wetness`, `soil_moisture_pct`, `soil_temp_c`, `ppfd`, `co2_ppm?`, `npk_n_ppm?`, `npk_p_ppm?`, `npk_k_ppm?`, `water_flow_l_total?`, `water_flow_l_per_min?`, `pheromone_count`, `battery_v`, `rssi`.

## Risk engine interfaces (already defined)
`from app.risk_engine import RiskModel, RiskContext, RiskResult, ReadingPoint, WeatherPoint, registry`
- A model subclasses `RiskModel`, sets class attrs `model_type`, `name`, `default_params` (dict), implements `evaluate(self, ctx: RiskContext) -> RiskResult | None`, and is decorated `@registry.register`.
- `ctx.readings`: ascending `ReadingPoint` list (recent window). `ctx.params`: resolved params. `ctx.forecast`: `WeatherPoint` list. `ctx.crop`, `ctx.crop_stage`, `ctx.now`.
- `RiskResult` fields: `model_type, level (RiskLevel), score, title, action_code, message_en, message_sw, dedup_key, window_start?, window_end?, details`. `is_actionable` => level >= MEDIUM.

## Cross-module service seams (implement EXACTLY these signatures; callers depend on them)
Ingestion (`app.ingestion.writer`):
- `def persist_reading(session, *, org_id, telem: TelemetryIn) -> bool` — sync; resolve Device by `device_uid == telem.device_id`; idempotent insert into readings (return False on duplicate); denormalize org_id + greenhouse_id; update Device last_seen_at/last_battery_v/last_rssi. Catch IntegrityError → rollback → False (works on PG + sqlite).
- `app.ingestion.consumer:main()` — paho-mqtt loop; runnable `python -m app.ingestion.consumer`.

Risk engine:
- `app.risk_engine.engine.evaluate_greenhouse(session, greenhouse_id, now=None) -> list[RiskAssessment]` — sync; load recent readings + active CropCycle + resolved `RiskModelConfig` params + recent forecast; run enabled models; persist `RiskAssessment`; for actionable results upsert `Alert` (dedupe by `dedup_key` within a cooldown) + `Recommendation` (en+sw). 
- `app.risk_engine.defaults.seed_risk_configs(session, org_id=None) -> None` — create `RiskModelConfig` rows from each model's `default_params`.
- Celery task name `app.risk_engine.tasks.evaluate_all_greenhouses`.

Alerting:
- `app.alerting.dispatcher.dispatch_alert(session, alert) -> Alert` — sync; load recommendation; pick recipients (org users) + channel per user prefs/quiet-hours; render templated message in user language; send via `channel_registry`; append to `alert.dispatch_log`; set status SENT/FAILED; handle dedup/escalation.
- `app.alerting.dispatcher.dispatch_pending(session) -> int`.
- Adapters self-register into `channel_registry` on import of `app.alerting.adapters`. Console always available; SMS/WhatsApp fall back to console when unconfigured.
- Celery task name `app.alerting.tasks.dispatch_pending_alerts`.
- USSD pull menu: `app.alerting.ussd.handle_ussd(session, *, session_id, phone, text) -> str` returning `CON ...`/`END ...` (latest readings, current risk, alerts, subscription balance).

Billing:
- `app.billing.service.org_has_feature(db, org_id, feature: str) -> bool` — **async**; True if org has an active/trial subscription whose plan grants `feature` (see `PLAN_FEATURES`/`PREMIUM_FEATURES` in `app.billing.base`).
- `app.billing.service.initiate_subscription(db, *, org_id, user_id, plan_type, phone, amount, plan_name="standard") -> tuple[Subscription, Payment, STKPushResult]` — async.
- `app.billing.service.handle_stk_callback(db, payload: dict) -> Payment` — async; reconcile by `checkout_request_id`; on success activate subscription (state machine trial→active) + mark installment paid.
- `app.billing.providers.get_payment_provider() -> PaymentProvider` — returns `MpesaProvider` when creds set else `MockPaymentProvider`.
- Celery task name `app.billing.tasks.reconcile_pending_payments`.

Control:
- `app.control.service.enqueue_command(db, *, org_id, actuator_device_id, command, source, issued_by=None, params=None) -> ControlCommand` — async.
- `app.control.service.execute_command(db, command_id) -> ControlCommand` — async; apply via `driver_registry` (mock acks immediately, updates `ActuatorDevice.state`), set status ACKED/FAILED.
- Drivers self-register into `driver_registry` on import of `app.control.drivers`. `mock` driver always present.
- `app.control.automation.evaluate_rules(session, greenhouse_id) -> list[ControlCommand]` — Wave 1 scaffold (enabled rules, safety interlocks) with TODOs; safe no-op when no enabled rules.

Weather:
- `app.weather.providers.build_provider(name) -> WeatherProvider` (`mock`/`openweather`/`tomorrowio`; mock is deterministic, no RNG).
- `app.weather.service.poll_farm(db, farm) -> None` — async; store `WeatherObservation` + `WeatherForecast`.
- Celery task name `app.weather.tasks.poll_all_farms`.

## REST API (base prefix `/api/v1`; JWT bearer via `app.api.deps`)
Use `from app.api.deps import CurrentUser, Scope, DBSession, require_role, require_feature`. Each router file defines a module-level `router = APIRouter(...)`. Response/request DTOs go in `app/api/schemas/<domain>.py`. Org-scope EVERY query.
- `POST /auth/login` (OAuth2 password form: username=email) → `{access_token, refresh_token, token_type}`. `POST /auth/register`, `GET /auth/me`, `POST /auth/refresh`.
- `GET /organizations/me`, org CRUD (super_admin).
- `GET/POST /farms`, `GET /farms/{id}`, `PATCH/DELETE`. Same for `/greenhouses`, `/devices`.
- `GET /greenhouses/{id}/readings?metric=&start=&end=&limit=` (timeseries), `GET /greenhouses/{id}/readings/latest`. Optional `POST /ingest` (HTTP telemetry).
- `GET /greenhouses/{id}/risk` (current assessments per model), `GET /greenhouses/{id}/risk/history` (gate history with `require_feature("dashboard_history")`).
- `GET /alerts?status=`, `POST /alerts/{id}/ack`.
- `GET /recommendations`, `POST /recommendations/{id}/override` (agronomist/coop_admin).
- `GET /greenhouses/{id}/actuators`, `POST /actuators/{id}/command` (manual; body `{command, params?}`), `GET /control/commands`.
- `GET /billing/subscription`, `POST /billing/subscribe` (body `{plan_type, phone, amount}` → triggers STK), `POST /billing/mpesa/callback` (NO auth — Daraja webhook), `GET /billing/payments`.
- `GET /farms/{id}/weather` (latest obs + forecast).
- `POST /ussd` (Africa's Talking webhook, form-encoded → text/plain menu), `GET+POST /whatsapp/webhook` (Meta verify + inbound).
- `records` router: scaffold `GET/POST /spray-logs`, `/harvest-logs`, `/expenses` minimally (real CRUD where easy; `501` + TODO otherwise).

## Demo constants (seed + simulator + demo MUST agree)
- Org slug: `demo-coop`; Farm near Nakuru, Kenya `lat=-0.303, lon=36.080`.
- Greenhouse name `GH-1`. Device uid `GH1-NODE-01` (sensor_node). Vent actuator `GH1-VENT-01`.
- Users (password `password123`): `admin@demo-coop.ke` (coop_admin), `agronomist@demo-coop.ke` (agronomist), `farmer@demo-coop.ke` (farmer, phone `+254700000001`).
- Tomato crop with stage NPK targets + stage durations. CropCycle planted ~45 days before "now", stage `flowering`.
Put these in `app/seed/constants.py` so everything imports one source of truth.

## Agronomic defaults (Kenya — document as field-calibratable placeholders)
- **Late blight**: wet-hour when `rh_pct >= 90` AND `10 <= air_temp_c <= 26`. Accumulate consecutive/rolling wet hours; `>= 10h` → HIGH ("ventilate now / apply preventive fungicide tonight"); 6–10h → MEDIUM. Fuse forecast: if forecast RH/temp imply the window will form overnight, pre-warn. Params: `rh_threshold=90, temp_min=10, temp_max=26, high_hours=10, med_hours=6, cooldown_hours=12`.
- **Tuta absoluta**: degree-days above `base_temp_c=10.0` accumulated since last generation reset; generation threshold `~208 DD` (placeholder, calibrate). Crossing → "new generation emerging, spray window open, check traps". `pheromone_count > trap_threshold (default 30)` elevates pressure. Params: `base_temp_c=10, generation_dd=208, trap_threshold=30`.
- **Microclimate (also runs on firmware)**: `air_temp_c > 35` → "vent now" (HIGH); `rh_pct > rh_warn (default 85)` → fungal warning (MEDIUM); `soil_moisture_pct < soil_min (default 25)` → "irrigate" (MEDIUM/HIGH).
- **Nutrient**: compare latest NPK to crop-stage targets (from `Crop.npk_targets[stage]`); deficits → fertigation recommendation.
- **Water**: combine `water_flow_l_per_min` + `soil_moisture_pct`: low soil + no flow → irrigate; flow with no scheduled irrigation → leak (HIGH); roll up per-cycle water totals for a savings report in `details`.

## What to return
Return a JSON object: `{module, files:[paths created], summary, tests_passed (bool|null), notes}`.
```
