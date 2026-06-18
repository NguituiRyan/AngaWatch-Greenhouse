// ============================================================================
// thresholds.h — instant (single-reading) microclimate threshold rules
// ----------------------------------------------------------------------------
// These constants MIRROR the backend "microclimate" risk model
// (docs/CONTRACT.md → Agronomic defaults → Microclimate):
//
//     air_temp_c  > 35  -> "vent now"        (HIGH)
//     rh_pct      > 85  -> fungal warning    (MEDIUM)
//     soil_moisture_pct < 25 -> "irrigate"   (MEDIUM/HIGH)
//
// The cloud risk engine is the source of truth for windowed/forecast-fused
// models (late blight, Tuta absoluta). The node only re-implements the *instant*
// rules so it can fire a local relay/buzzer when the network is down. Keep these
// numbers in sync with RiskModelConfig defaults; they are field-calibratable.
// ============================================================================

#ifndef ANGAWATCH_THRESHOLDS_H
#define ANGAWATCH_THRESHOLDS_H

// ---- Air temperature: ventilate to avoid heat stress / flower abortion ----
#define AIR_TEMP_VENT      35.0f   // °C, > -> HIGH, trip vent/relay

// ---- Relative humidity: fungal (Botrytis/blight) pressure warning ----
#define RH_FUNGAL_WARN     85.0f   // %RH, > -> MEDIUM warning

// ---- Soil moisture: irrigation trigger ----
#define SOIL_IRRIGATE_MIN  25.0f   // %VWC, < -> irrigate (MEDIUM)
#define SOIL_IRRIGATE_CRIT 15.0f   // %VWC, < -> irrigate (HIGH, crop at risk)

// ----------------------------------------------------------------------------
// Severity levels reported alongside any local alert. Numeric values are ordered
// so the firmware can pick the single highest-severity condition to drive the
// relay and the serial banner.
// ----------------------------------------------------------------------------
enum AlertLevel {
  ALERT_NONE   = 0,
  ALERT_LOW    = 1,
  ALERT_MEDIUM = 2,
  ALERT_HIGH   = 3,
};

#endif  // ANGAWATCH_THRESHOLDS_H
