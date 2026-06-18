// ============================================================================
// sensors.h — sensor abstraction for the AngaWatch greenhouse node
// ----------------------------------------------------------------------------
// Reads every sensor on the node into a single SensorReadings struct whose field
// names line up 1:1 with app/schemas/telemetry.py (TelemetryIn). A field set to
// NAN (float) / NPK_NA (int) means "sensor absent or read failed" and is encoded
// as JSON null so the backend treats it as a missing optional reading.
// ============================================================================

#ifndef ANGAWATCH_SENSORS_H
#define ANGAWATCH_SENSORS_H

#include <Arduino.h>

// Sentinel for an unavailable integer reading (NPK ppm, pheromone count, rssi).
constexpr int32_t NPK_NA = INT32_MIN;

// ----------------------------------------------------------------------------
// One full sample from one node. Field names == telemetry contract fields.
// Floats default to NAN (missing); use isnan() / NPK_NA to detect gaps.
// ----------------------------------------------------------------------------
struct SensorReadings {
  // ---- Microclimate (air) ----
  float   air_temp_c        = NAN;   // SHT4x
  float   rh_pct            = NAN;   // SHT4x
  float   leaf_wetness      = NAN;   // 0..100 % (analog grid)
  float   ppfd             = NAN;   // µmol·m⁻²·s⁻¹
  float   co2_ppm          = NAN;   // optional NDIR sensor

  // ---- Soil ----
  float   soil_moisture_pct = NAN;   // capacitive probe, %VWC
  float   soil_temp_c       = NAN;   // DS18B20
  int32_t npk_n_ppm         = NPK_NA;  // RS485 Modbus
  int32_t npk_p_ppm         = NPK_NA;
  int32_t npk_k_ppm         = NPK_NA;

  // ---- Water (placeholder until a flow meter is wired) ----
  float   water_flow_l_total   = NAN;
  float   water_flow_l_per_min = NAN;

  // ---- Pest ----
  int32_t pheromone_count   = 0;     // cumulative trap catches this cycle

  // ---- Device health ----
  float   battery_v         = NAN;   // pack voltage via divider
  int32_t rssi             = NPK_NA; // filled in by lora.cpp after TX
};

namespace sensors {

// Power up / configure all sensor peripherals (I2C, OneWire, RS485, ADC).
// Call once early in setup() / each wake before sampleAll().
void begin();

// Read every sensor and return a fully-populated SensorReadings. Individual
// failed reads leave their field at the NAN / NPK_NA sentinel. Best-effort: a
// dead sensor never aborts the cycle.
SensorReadings sampleAll();

// Latch + read the deep-sleep-surviving pheromone trap pulse counter, then add
// it to the running total kept in RTC memory. Exposed separately because the
// counter is incremented by a hardware interrupt independent of sampleAll().
int32_t readPheromoneCounter();

// Put sensor rails to sleep / float direction pins before deep sleep to minimize
// quiescent current.
void powerDown();

}  // namespace sensors

#endif  // ANGAWATCH_SENSORS_H
