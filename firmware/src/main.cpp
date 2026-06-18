// ============================================================================
// main.cpp — AngaWatch greenhouse node RTC/deep-sleep flow
// ----------------------------------------------------------------------------
// Lifecycle of one wake cycle:
//   1. setup(): init serial, sensors, LoRa, (optional) OTA.
//   2. sample every sensor.
//   3. run INSTANT microclimate threshold rules LOCALLY -> drive relay/buzzer +
//      serial banner so the farmer gets an alert even with no network.
//   4. build an ArduinoJson telemetry document with the contract fields.
//   5. transmit it over LoRa to the gateway.
//   6. deep sleep until the next interval.
//
// This is a "wake → do everything in setup() → sleep" design, so loop() never
// really runs; it exists only as a safety net to force sleep if execution ever
// falls through.
// ============================================================================

#include <Arduino.h>
#include <ArduinoJson.h>

#include "config.h"
#include "thresholds.h"
#include "sensors.h"
#include "lora.h"

#if OTA_ENABLED
#include <WiFi.h>
#include <ArduinoOTA.h>
#endif

// Boot counter persisted across deep sleep, handy for diagnostics + de-dup hints.
RTC_DATA_ATTR static uint32_t g_boot_count = 0;

// ----------------------------------------------------------------------------
// Local instant-threshold evaluation. Mirrors the backend microclimate model
// (thresholds.h). Returns the single highest severity found and trips the local
// alert relay/buzzer accordingly. Each fired rule is also printed for the field
// technician's serial console.
// ----------------------------------------------------------------------------
static AlertLevel evaluateThresholds(const SensorReadings &r) {
  AlertLevel level = ALERT_NONE;
  auto raise = [&](AlertLevel l) { if (l > level) level = l; };

  // --- Heat stress: air_temp_c > 35 -> vent now (HIGH) ---
  if (!isnan(r.air_temp_c) && r.air_temp_c > AIR_TEMP_VENT) {
    Serial.printf("[ALERT][HIGH] air_temp %.1f C > %.1f -> VENT NOW\n",
                  r.air_temp_c, AIR_TEMP_VENT);
    raise(ALERT_HIGH);
  }

  // --- Fungal pressure: rh_pct > 85 -> warning (MEDIUM) ---
  if (!isnan(r.rh_pct) && r.rh_pct > RH_FUNGAL_WARN) {
    Serial.printf("[ALERT][MED ] rh %.1f%% > %.1f -> fungal risk\n",
                  r.rh_pct, RH_FUNGAL_WARN);
    raise(ALERT_MEDIUM);
  }

  // --- Soil moisture: < 25 irrigate (MEDIUM), < 15 critical (HIGH) ---
  if (!isnan(r.soil_moisture_pct)) {
    if (r.soil_moisture_pct < SOIL_IRRIGATE_CRIT) {
      Serial.printf("[ALERT][HIGH] soil %.1f%% < %.1f -> IRRIGATE (critical)\n",
                    r.soil_moisture_pct, SOIL_IRRIGATE_CRIT);
      raise(ALERT_HIGH);
    } else if (r.soil_moisture_pct < SOIL_IRRIGATE_MIN) {
      Serial.printf("[ALERT][MED ] soil %.1f%% < %.1f -> irrigate soon\n",
                    r.soil_moisture_pct, SOIL_IRRIGATE_MIN);
      raise(ALERT_MEDIUM);
    }
  }

  // Drive the local actuator: any MEDIUM+ condition energizes the relay/buzzer.
  // For HIGH conditions a real vent relay would latch; a buzzer would pulse.
  digitalWrite(PIN_ALERT_RELAY, level >= ALERT_MEDIUM ? HIGH : LOW);

  if (level == ALERT_NONE) {
    Serial.println("[ok] all instant thresholds within range");
  }
  return level;
}

// ----------------------------------------------------------------------------
// Build the telemetry JSON document. Field names + types MUST match
// app/schemas/telemetry.py (TelemetryIn). Missing sensor values are emitted as
// JSON null so the backend treats them as absent optionals. We also include
// org_id + device routing hints the gateway uses to build the MQTT topic
// farm/{org_id}/{device_id}/telemetry, plus a local alert flag for offline UX.
// ----------------------------------------------------------------------------
static String buildTelemetryJson(const SensorReadings &r, AlertLevel localAlert) {
  // ArduinoJson v7 elastic document; payload stays well under the LoRa MTU.
  JsonDocument doc;

  // ---- Routing / identity (consumed by the gateway, ignored by TelemetryIn) --
  doc["org_id"] = ORG_ID;
  doc["device_id"] = DEVICE_UID;           // == TelemetryIn.device_id
  doc["fw"] = FW_VERSION;
  doc["boot"] = g_boot_count;

  // ---- Timestamp ----
  // A LoRa-only node usually has no RTC clock; send millis() since boot and let
  // the gateway stamp wall-clock time. If an RTC/GPS is fitted, put epoch here —
  // TelemetryIn.ts accepts epoch seconds, millis, or ISO-8601.
  doc["ts"] = millis();

  // ---- Microclimate ----
  auto putF = [&](const char *k, float v) {
    if (isnan(v)) doc[k] = nullptr; else doc[k] = serialized(String(v, 2));
  };
  auto putI = [&](const char *k, int32_t v) {
    if (v == NPK_NA) doc[k] = nullptr; else doc[k] = v;
  };

  putF("air_temp_c", r.air_temp_c);
  putF("rh_pct", r.rh_pct);
  putF("leaf_wetness", r.leaf_wetness);
  putF("ppfd", r.ppfd);
  putF("co2_ppm", r.co2_ppm);

  // ---- Soil ----
  putF("soil_moisture_pct", r.soil_moisture_pct);
  putF("soil_temp_c", r.soil_temp_c);
  putI("npk_n_ppm", r.npk_n_ppm);
  putI("npk_p_ppm", r.npk_p_ppm);
  putI("npk_k_ppm", r.npk_k_ppm);

  // ---- Water ----
  putF("water_flow_l_total", r.water_flow_l_total);
  putF("water_flow_l_per_min", r.water_flow_l_per_min);

  // ---- Pest ----
  doc["pheromone_count"] = r.pheromone_count;

  // ---- Device health ----
  putF("battery_v", r.battery_v);
  putI("rssi", r.rssi);

  // ---- Local instant-alert hint (offline UX; backend re-derives via risk eng) -
  doc["local_alert"] = static_cast<int>(localAlert);

  String out;
  serializeJson(doc, out);
  return out;
}

// ----------------------------------------------------------------------------
// Enter deep sleep for the configured interval. ext1 wake on the pheromone trap
// pin could be added here so beam-breaks also wake the node; for now we wake
// purely on the timer.
// ----------------------------------------------------------------------------
static void goToDeepSleep() {
  sensors::powerDown();
  lora::sleep();
  Serial.printf("[sleep] deep sleep for %llu min\n", DEEP_SLEEP_MINUTES);
  Serial.flush();
  esp_sleep_enable_timer_wakeup(DEEP_SLEEP_INTERVAL_US);
  esp_deep_sleep_start();  // never returns; MCU reboots into setup() on wake
}

#if OTA_ENABLED
// OTA-READY: bring up WiFi + ArduinoOTA. Only compiled for WiFi-backhaul nodes.
static void setupOta() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  // Bounded wait so a flaky AP can't keep the node awake forever.
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 8000) delay(200);
  if (WiFi.status() == WL_CONNECTED) {
    ArduinoOTA.setHostname(OTA_HOSTNAME);
    // ArduinoOTA.setPassword(...);  // set via build flag / secrets in production
    ArduinoOTA.begin();
    Serial.printf("[ota] ready at %s\n", WiFi.localIP().toString().c_str());
  }
}
#endif

// ----------------------------------------------------------------------------
// setup(): runs on every wake (deep sleep => fresh boot). Does the full cycle.
// ----------------------------------------------------------------------------
void setup() {
  const uint32_t wakeStart = millis();
  g_boot_count++;

  Serial.begin(115200);
  delay(50);
  Serial.printf("\n=== AngaWatch node %s (org %s) fw %s boot #%u ===\n",
                DEVICE_UID, ORG_ID, FW_VERSION, g_boot_count);

  // 1. Init peripherals.
  sensors::begin();
  const bool radioOk = lora::begin();
  if (!radioOk) Serial.println("[warn] LoRa init failed — will still sleep");

#if OTA_ENABLED
  // OTA-READY hook: for WiFi nodes, expose an update window before sleeping.
  setupOta();
#endif

  // 2. Sample sensors.
  SensorReadings r = sensors::sampleAll();
  r.rssi = radioOk ? lora::lastRssi() : NPK_NA;

  // 3. Run instant threshold rules locally (offline alerting).
  const AlertLevel localAlert = evaluateThresholds(r);

  // 4. Build telemetry document.
  const String payload = buildTelemetryJson(r, localAlert);
  Serial.printf("[telemetry] %s\n", payload.c_str());

  // 5. Transmit over LoRa.
  if (radioOk) {
    const bool sent = lora::sendPacket(payload);
    Serial.println(sent ? "[lora] packet sent" : "[lora] TX failed");
  }

#if OTA_ENABLED
  // OTA-READY hook: give an in-progress update a brief chance to start before we
  // sleep. Skip the sleep entirely while an OTA is uploading in a real build.
  ArduinoOTA.handle();
#endif

  // Safety: never exceed the awake budget regardless of what happened above.
  if (millis() - wakeStart > MAX_AWAKE_MS) {
    Serial.println("[warn] exceeded awake budget");
  }

  // 6. Deep sleep.
  goToDeepSleep();
}

// loop() is effectively dead code under the deep-sleep model: setup() always
// ends in esp_deep_sleep_start(). Kept as a defensive fallback that re-sleeps if
// we ever reach here (e.g. someone disables deep sleep for debugging).
void loop() {
#if OTA_ENABLED
  ArduinoOTA.handle();
#endif
  goToDeepSleep();
}
