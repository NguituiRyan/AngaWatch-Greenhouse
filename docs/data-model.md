# Data model

The schema is SQLAlchemy 2.0 (`Mapped` / `mapped_column`), UUID primary keys, and
a consistent Alembic naming convention (`app/db/base.py`). 33 tables span the full
platform — Wave 0 tables are actively used; Wave 1–3 tables are in place ahead of
their service/API layers. Migrations live in `backend/alembic/versions/`
(`0001_initial`, `0002_timescale_hypertable`).

See also: [`risk-models.md`](risk-models.md) (how the intelligence tables are
produced) and [`../NOTES.md`](../NOTES.md) (which tables have services yet).

---

## Entity overview

### Core hierarchy

```
Organization ──▶ Farm ──▶ Greenhouse ──▶ Device ──▶ Reading (hypertable)
     │                          │
     ├─▶ User                   └─▶ CropCycle ──▶ Crop
     └─▶ Subscription
```

| Entity | Purpose | Key fields |
| ------ | ------- | ---------- |
| `Organization` | Tenant root (cooperative / reseller). | `slug` (unique), `is_reseller`, `white_label`, `theme`, `timezone`. |
| `User` | farmer / agronomist / coop_admin / super_admin. Carries channel + language + quiet-hours prefs. | `email`, `phone`, `role`, `preferred_language`, `preferred_channel`, `notify_*`, `quiet_hours_*`. |
| `Farm` | A physical site with coordinates. | `latitude`, `longitude`, `county`, `area_ha`. |
| `Greenhouse` | The unit the risk engine evaluates. | `farm_id`, `zone`, `structure_type`, `area_m2`. |
| `Device` | A sensor/gateway/actuator node. `device_uid` is the MQTT id. | `device_uid` (unique), `device_type`, `status`, denormalised `last_seen_at`/`last_battery_v`/`last_rssi`. |
| `Reading` | Time-series telemetry (the hypertable). | PK `(device_id, time)`; denormalised `org_id` + `greenhouse_id`; all sensor channels. |
| `Crop` | Shared agronomic catalog entry (`org_id` nullable ⇒ global). | `npk_targets` (stage → {n,p,k}), `stage_durations_days`. |
| `CropCycle` | A planting in one greenhouse. | `crop_id`, `planting_date`, `current_stage`, `is_active`. |

### Intelligence (the IP layer)

| Entity | Purpose |
| ------ | ------- |
| `RiskModelConfig` | Calibratable params per model, scoped greenhouse > org > global. `enabled` + `params` (JSON). |
| `RiskAssessment` | One model verdict for a greenhouse at a time: `model_type`, `level`, `score`, `window_*`, `details`. |
| `Alert` | A dispatchable, deduplicated alert (`dedup_key`, `status`, `escalation_level`, `dispatch_log`). |
| `Recommendation` | Bilingual action (`message_en` + `message_sw`, `action_code`, `priority`); supports agronomist `override_*`. |

### Control

| Entity | Purpose |
| ------ | ------- |
| `ActuatorDevice` | A vent/fan/valve/pump with `state` + `config` (safety interlocks). |
| `AutomationRule` | `condition → action` with `safety_interlocks` (Wave 1 auto-fire). |
| `ControlCommand` | A queued/sent/acked actuation, `source` auto/manual. |

### Weather

| Entity | Purpose |
| ------ | ------- |
| `WeatherObservation` | A point-in-time observation per farm + source. |
| `WeatherForecast` | An hourly forecast point (`forecast_for`), fused into the blight/water models. |

### Records (Wave 1, wired)

`FarmRecord` (generic journal), `SprayLog` (with `phi_days` pre-harvest interval),
`HarvestLog`, `Expense`.

### Billing

| Entity | Purpose |
| ------ | ------- |
| `Subscription` | Plan (`subscription`/`rent_to_own`/`daas`), `status` state machine, `features`, trial/period dates. |
| `Installment` | Rent-to-own schedule line (`sequence`, `amount`, `paid`). |
| `Payment` | An M-Pesa STK attempt + reconciliation (`checkout_request_id`, `mpesa_receipt`, `result_code`). |

### Commerce / Finance (Wave 2–3, model-only)

`Invoice`, `InputProduct`, `InputOrder`, `Buyer`, `MarketListing`, `DryerUnit`
(commerce); `FinancingProfile`, `CreditScore`, `TraceabilityRecord` (finance &
GlobalGAP/organic export). These have ORM tables but no service/API layer yet.

---

## The multi-tenant `org_id` rule

**Every query against a tenant table must filter by `org_id`.** This is the single
most important invariant in the codebase, enforced mechanically at three levels:

1. **On the model.** `OrgScopedMixin` adds a non-nullable `org_id` FK
   (`ON DELETE CASCADE`, indexed) to every tenant-owned table.
2. **On the hot path.** `org_id` (and `greenhouse_id`) are **denormalised onto
   `readings`** so per-tenant and per-greenhouse window queries never join back
   through `devices`. The ingestion writer copies them from the resolved device,
   and rejects a reading whose topic `org_id` does not match the device's org.
3. **In the API.** `app.api.deps.get_org_scope` bundles the request session with
   the authenticated user's `org_id` into an `OrgScope`; handlers filter every
   `select()` by `scope.org_id`. Cross-tenant access returns 404, not 403, so
   resource existence is not leaked.

`Crop`, `InputProduct` and `RiskModelConfig` allow a **null `org_id`** to mean a
*global / shared* row (e.g. the default tomato catalog entry, or the global risk
defaults) that applies until a more specific org/greenhouse row overrides it.

Enums are stored as `VARCHAR` of their `.value` (not native PG enums) via
`enum_column`, so risk/alert/billing enums can be extended without `ALTER TYPE`
migrations.

---

## The Timescale hypertable (`readings`)

`readings` is a **TimescaleDB hypertable** partitioned on `time`. It is the only
table that is *not* a plain relational table, because telemetry is high-volume,
append-mostly, and queried by time window.

Defined in `app/db/models/reading.py` and converted by the Alembic migration
`0002_timescale_hypertable.py`:

- **Composite PK `(device_id, time)`** — makes ingestion idempotent: a duplicate
  re-delivery raises `IntegrityError` (caught and reported as a no-op) on both
  PostgreSQL and SQLite. No dialect-specific `ON CONFLICT` is used, so the SQLite
  test path and the Timescale deployment exercise the same code.
- **Denormalised `org_id` + `greenhouse_id`** — plus the supporting indexes
  `ix_readings_greenhouse_time` and `ix_readings_org_time` for fast window scans.
- **Hypertable settings** (PostgreSQL only; a no-op on SQLite in tests):
  - `create_hypertable('readings', 'time', chunk_time_interval => 7 days)`,
  - **compression** of chunks older than 14 days (`compress_segmentby = device_id`),
  - **retention** dropping raw data older than 365 days.

The reading columns mirror the telemetry contract exactly: microclimate
(`air_temp_c`, `rh_pct`, `leaf_wetness`, `ppfd`, `co2_ppm`), soil
(`soil_moisture_pct`, `soil_temp_c`, `npk_*_ppm`), water (`water_flow_l_total`,
`water_flow_l_per_min`), pest (`pheromone_count`), and device health (`battery_v`,
`rssi`), plus an `ingested_at` stamp.
