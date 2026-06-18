# Risk models — the agronomic moat

AngaWatch ships five risk models. Each is a **pure function** of
`(readings, params, forecast)` — no ORM or DB import — so it is unit-testable with
synthetic data. A model subclasses `RiskModel`, sets `model_type` / `name` /
`default_params`, implements `evaluate(ctx) -> RiskResult | None`, and
self-registers with `@registry.register`. The orchestrator
(`engine.evaluate_greenhouse`) builds the `RiskContext`, runs every enabled model,
persists a `RiskAssessment`, and (for MEDIUM+ results) raises a deduplicated
`Alert` + bilingual `Recommendation`.

**Levels & actionability.** `RiskLevel` ranks `none < low < medium < high <
critical`. A result is *actionable* (becomes an alert) at **MEDIUM or above**;
lower levels are logged assessments only.

**Calibration.** Every threshold below is a **field-calibratable placeholder**
stored in `RiskModelConfig.params`, resolved as
`{**default_params, **config.params}` with precedence **greenhouse > org >
global**. Recalibrating is a DB row update, not a redeploy. The references at the
end of each section are **placeholders** — fill them with the specific Kenyan
extension-service / journal sources used to validate the numbers.

---

## 1. Late blight — `model_type = late_blight`

*Phytophthora infestans* sporulates when foliage stays wet and cool for a
sustained period.

**Inputs:** the recent reading window (`rh_pct`, `air_temp_c`) and the upcoming
`forecast` (`rh_pct`, `air_temp_c`).

**Math.**
- An hour is a **wet hour** when `rh_pct ≥ rh_threshold` *and*
  `temp_min ≤ air_temp_c ≤ temp_max`.
- Iterate the window from the most recent reading backwards, counting the
  **trailing run** of consecutive wet hours (`wet_run`); stop at the first dry
  hour.
- **Forecast fusion:** count the *leading* contiguous run of wet hours in the
  forecast within `forecast_lookahead_hours` of `now` (`forecast_wet`), stopping at
  the first non-wet forecast hour.
- `effective = wet_run + forecast_wet`.
- `score = min(1.0, effective / high_hours)`.

**Thresholds / outputs.**
| `effective` wet hours | Level | Action |
| --------------------- | ----- | ------ |
| `< med_hours` (6) | none (returns `None`) | — |
| `med_hours`–`high_hours` (6–10) | **MEDIUM** | `ventilate_now` — open vents to dry the canopy, prepare a preventive spray. |
| `≥ high_hours` (10) | **HIGH** | `ventilate_and_spray` — ventilate now and apply a preventive fungicide tonight. |

`details` carries `wet_hours`, `forecast_wet_hours`, `effective_wet_hours`, the
thresholds, and `forecast_fused`.

**Default params:** `rh_threshold=90.0`, `temp_min=10.0`, `temp_max=26.0`,
`high_hours=10`, `med_hours=6`, `cooldown_hours=12`, `forecast_lookahead_hours=12`.

**Kenya calibration notes.** The consecutive-wet-hour rule is a defensible
approximation of disease pressure but is **not** a calibrated
Smith-period / BLITECAST model. The hour thresholds are the primary tuning target
for highland tomato; `temp_max=26` reflects the cool-favouring nature of the
pathogen. _References: placeholder — TODO add Kenyan late-blight forecasting
extension references._

---

## 2. Tuta absoluta — `model_type = tuta_absoluta`

The tomato leafminer's development is heat-driven; a new generation emerges after a
fixed accumulation of growing degree-days, and pheromone-trap catches confirm adult
flight.

**Inputs:** the reading window (`air_temp_c`, `pheromone_count`), plus an optional
carry-in of prior degree-days via `ctx.extra["tuta_dd_carry"]`.

**Math.**
- **Degree-days** are integrated per inter-sample interval:
  `Σ max(0, mean_temp − base_temp) × (Δhours / 24)`, where `mean_temp` is the
  average of consecutive samples' `air_temp_c`. This is robust to irregular
  sampling. Readings without a temperature are skipped.
- `dd = tuta_dd_carry + accumulated`; `fraction = dd / generation_dd`.
- **Trap pressure:** `max_trap = max(pheromone_count)` in the window;
  `trap_elevated = max_trap > trap_threshold`.
- `score = min(1.0, fraction)`, raised to `≥ 0.9` when traps are elevated.

**Thresholds / outputs.** Requires ≥2 readings.
| Condition | Level | Action |
| --------- | ----- | ------ |
| `dd ≥ generation_dd` (generation crossed) | **HIGH** | `tuta_spray_window` — new generation emerging, spray window open, scout + check traps. |
| `trap_elevated` (and not yet crossed) | **HIGH** | `tuta_scout_and_spray` — adult flight detected. |
| `fraction ≥ warn_fraction` (0.75) | **MEDIUM** | `tuta_monitor` — generation building, increase trap checks. |
| none of the above | none (`None`) | — |

`details` carries `degree_days`, `generation_dd`, `generation_fraction`,
`generation_crossed`, `max_pheromone_count`, `trap_elevated`.

**Default params:** `base_temp_c=10.0`, `generation_dd=208.0`, `trap_threshold=30`,
`warn_fraction=0.75`, `cooldown_hours=24`.

**Kenya calibration notes.** `generation_dd=208` is the single most important
placeholder — published estimates for a full *Tuta absoluta* generation vary, so
confirm against local conditions and variety. `base_temp_c=10` is the standard
lower development threshold. _References: placeholder — TODO add *Tuta absoluta*
degree-day / KEPHIS references._

---

## 3. Microclimate — `model_type = microclimate`

A latest-reading guardrail that **also runs on the node firmware** for offline
protection (`firmware/include/thresholds.h` mirrors these bands).

**Inputs:** the single latest reading (`air_temp_c`, `rh_pct`, `soil_moisture_pct`).

**Math / thresholds.** Each triggered condition is collected; the
**highest-severity** one becomes the headline verdict, the rest are listed in
`details["triggers"]`.
| Condition | Level | Action |
| --------- | ----- | ------ |
| `air_temp_c > temp_high` (35) | **HIGH** | `vent_now` — overheating, prevent heat stress / flower drop. |
| `soil_moisture_pct < soil_critical` (15) | **HIGH** | `irrigate_now` — root zone critically dry. |
| `soil_moisture_pct < soil_min` (25) | **MEDIUM** | `irrigate` — soil moisture low, schedule irrigation. |
| `rh_pct > rh_warn` (85) | **MEDIUM** | `reduce_humidity` — humidity favours fungal disease, ventilate. |

`score = 1.0` for HIGH, `0.6` for MEDIUM.

**Default params:** `temp_high=35.0`, `rh_warn=85.0`, `soil_min=25.0`,
`soil_critical=15.0`, `cooldown_hours=6`.

**Kenya calibration notes.** These instant bands are duplicated on-firmware and
**must be kept in sync** if re-tuned. They are intentionally conservative
single-point guards, complementary to the windowed blight/Tuta models.
_References: placeholder — TODO add tomato heat-stress / VPD references._

---

## 4. Nutrient (NPK) — `model_type = nutrient`

Compares the latest soil N/P/K against the crop-stage targets.

**Inputs:** the latest reading (`npk_n_ppm`, `npk_p_ppm`, `npk_k_ppm`) and the
stage targets the orchestrator places in `ctx.extra["npk_targets"]` (resolved from
`Crop.npk_targets[stage]`). Returns `None` if no targets are available.

**Math.** For each nutrient with a positive target and a measured value:
`relative = (target − value) / target`. A nutrient is **deficient** when
`relative > deficit_fraction`. The worst relative deficit drives the verdict;
`score = min(1.0, worst_relative / severe_fraction)`.

**Thresholds / outputs.**
| Worst relative deficit | Level | Action |
| ---------------------- | ----- | ------ |
| `> deficit_fraction` (0.15) | **MEDIUM** | `adjust_fertigation` — top up the deficient nutrient(s) in the fertigation mix. |
| `≥ severe_fraction` (0.35) | **HIGH** | `adjust_fertigation` (severe). |

The recommendation names the specific deficient nutrients (e.g. "N, K"); `details`
carries the per-nutrient `deficits`, `targets`, and `crop_stage`.

**Default params:** `deficit_fraction=0.15`, `severe_fraction=0.35`,
`cooldown_hours=24`.

**Kenya calibration notes.** The tolerances are generic; the per-stage *targets*
themselves (`TOMATO_NPK_TARGETS` in `app/seed/constants.py`, e.g. flowering ≈
`N 170 / P 80 / K 220` ppm) are placeholders for the `Anna F1` variety and should
be set from local soil-test / fertigation guidance. _References: placeholder — TODO
add tomato fertigation NPK schedule references._

---

## 5. Water — `model_type = water`

Fuses drip-line flow with soil moisture to choose between irrigate, leak, or
normal, and rolls up water use.

**Inputs:** the latest reading (`soil_moisture_pct`, `water_flow_l_per_min`), the
window's cumulative `water_flow_l_total`, and `ctx.extra["irrigation_scheduled"]`
(defaults to `False`).

**Math / decision.** With `flowing = water_flow_l_per_min > flow_active`:
| Situation | Condition | Level | Action |
| --------- | --------- | ----- | ------ |
| **Leak** | `flowing` and not `scheduled` and (soil unknown or `soil ≥ soil_wet`) | **HIGH** | `check_leak` — flow with no scheduled irrigation + wet soil ⇒ stuck valve / burst line. |
| **Irrigate (critical)** | `soil < soil_critical` and not `flowing` | **HIGH** | `irrigate` (immediately). |
| **Irrigate** | `soil < soil_min` and not `flowing` | **MEDIUM** | `irrigate` (soon). |
| **Normal** | otherwise | none (`None`) | — |

Regardless of verdict, `details` always carries the per-cycle water rollup
(`water_used_l = max(total) − min(total)`, plus window start/end totals) for a
dashboard savings figure.

**Default params:** `soil_min=25.0`, `soil_critical=15.0`, `soil_wet=35.0`,
`flow_active=0.5` L/min, `cooldown_hours=6`.

**Kenya calibration notes.** Leak detection depends on an accurate
`irrigation_scheduled` flag (currently defaulting to `False` until real irrigation
schedules are wired). The soil bands align with the microclimate model.
_References: placeholder — TODO add drip-irrigation / VWC references._

---

## How the orchestrator turns a `RiskResult` into an alert

`engine.evaluate_greenhouse` persists a `RiskAssessment` for **every** non-`None`
result. For actionable (MEDIUM+) results it:

1. computes the model's `cooldown_hours` from the resolved params,
2. looks for a recent un-acked `Alert` with the same `dedup_key` within that
   cooldown,
3. **refreshes** it if found (no duplicate), or **creates** a new `PENDING` alert,
4. attaches a `Recommendation` carrying `message_en` + `message_sw` + `action_code`
   + `priority` (the level rank). An agronomist override on a recommendation is
   preserved across refreshes (kept as a future training signal).

`dedup_key` is `"{model_type}:{greenhouse_id}:{level|action_code|code}"` depending
on the model, so distinct conditions raise distinct alerts while repeats of the
same condition collapse.
