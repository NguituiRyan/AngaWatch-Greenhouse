// ============================================================================
// main_wifi.cpp — AngaWatch greenhouse node, WiFi + MQTT backhaul variant
// ----------------------------------------------------------------------------
// A second, PARALLEL firmware path to the LoRa deep-sleep node in main.cpp. This
// board talks DIRECTLY to the MQTT broker (no LoRa gateway needed) and closes the
// full control loop with the dashboard:
//
//   * telemetry UP   -> publish TelemetryIn JSON to
//                       farm/{ORG_ID}/{DEVICE_UID}/telemetry      (every interval)
//   * commands DOWN  -> subscribe farm/{ORG_ID}/{DEVICE_UID}/command
//                       on open/close/on/off: drive PIN_VENT_RELAY
//   * state/ack UP   -> publish farm/{ORG_ID}/{DEVICE_UID}/state
//                       {command_id, actuator_uid, state, ok, ts}
//
// The backend consumer (app/ingestion/consumer.py) validates telemetry against
// app/schemas/telemetry.py and turns the state ack into a confirmed
// ActuatorDevice.state + an ACKED ControlCommand (app/control/ingest.py). This
// firmware mirrors scripts/esp_emulator.py byte-for-byte on the wire, which the
// loop verifier (scripts/verify_loop.py) already PASSES.
//
// POWER TRADE-OFF: unlike the LoRa node (which deep-sleeps for ~15 min between
// reads to stretch a tiny solar/battery budget), this node STAYS AWAKE so it can
// remain subscribed and receive a vent command the instant the dashboard issues
// it. That continuous MQTT/WiFi draw (~tens of mA) means the WiFi node wants
// mains power or a solar-buffered pack with a healthy battery — it is the "smart
// greenhouse controller", not the deep-field sipping sensor.
//
// Build with the [env:esp32-wifi] PlatformIO environment (see platformio.ini).
// Add -DSIMULATE_SENSORS to synthesise plausible readings so it runs the full
// closed loop with NO sensors physically wired.
//
// Authored for clarity — NOT compiled in CI. Verify pins/calibration on real HW.
// ============================================================================

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>          // time()/configTime() for the telemetry ts epoch

#include "config.h"
#include "thresholds.h"
#include "sensors.h"

#ifdef SIMULATE_SENSORS
#include <math.h>
#endif

#if OTA_ENABLED
#include <ArduinoOTA.h>
#endif

// ----------------------------------------------------------------------------
// Derived MQTT topics (built once from the identity in config.h / secrets.h).
// Topic shapes are FIXED by the verified backend contract — do not change them.
// ----------------------------------------------------------------------------
static const String TOPIC_TELEMETRY = String("farm/") + ORG_ID + "/" + DEVICE_UID + "/telemetry";
static const String TOPIC_COMMAND   = String("farm/") + ORG_ID + "/" + DEVICE_UID + "/command";
static const String TOPIC_STATE     = String("farm/") + ORG_ID + "/" + DEVICE_UID + "/state";

// ----------------------------------------------------------------------------
// MQTT transport. PubSubClient rides on a plain WiFiClient (TCP). For a TLS
// broker, swap WiFiClient -> WiFiClientSecure and set the CA / port 8883.
// PubSubClient's default MTU (256 B) is too small for our telemetry doc, so we
// bump it in setup() via setBufferSize().
// ----------------------------------------------------------------------------
static WiFiClient   wifiClient;
static PubSubClient mqtt(wifiClient);

// Virtual vent state mirrored in RAM so the ack reports what the relay actually
// is. HIGH(open)/LOW(closed) — see drivePin() below. Starts closed, matching the
// relay's de-energized boot state and the emulator's initial "closed".
static const char *g_ventState = "closed";

// Command verb -> resulting actuator state. MUST match the backend mapping
// (mqtt_relay.py _COMMAND_TO_STATE and esp_emulator.py _VERB_STATE):
//   open->open, close->closed, on->on, off->off
struct VerbState { const char *verb; const char *state; bool energize; };
static const VerbState VERB_TABLE[] = {
    {"open",  "open",   true},
    {"close", "closed", false},
    {"on",    "on",     true},
    {"off",   "off",    false},
};

// Monotonic schedule for the next telemetry publish (always-on node uses millis,
// not deep sleep). Set to 0 so the first loop() publishes immediately.
static uint32_t g_nextTelemetryMs = 0;
static uint32_t g_publishCount    = 0;

// ----------------------------------------------------------------------------
// Local instant-threshold evaluation. Identical rules to evaluateThresholds() in
// main.cpp / thresholds.h, kept inline here so the WiFi node ALSO trips the local
// alert relay/buzzer the moment a microclimate threshold is breached — even if
// WiFi or the broker is momentarily down. The cloud risk engine remains the
// source of truth for windowed/forecast models.
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

  // Any MEDIUM+ condition energizes the LOCAL alert relay/buzzer (offline UX).
  // NOTE: this is PIN_ALERT_RELAY (buzzer/siren), NOT PIN_VENT_RELAY — the vent
  // is driven by cloud commands so the dashboard stays the single owner of the
  // actuator's confirmed state. (A purely-local "auto-vent on heat" could also
  // drive PIN_VENT_RELAY here, but then we would have to publish an unsolicited
  // state ack to keep the dashboard honest; left out to keep ownership clear.)
  digitalWrite(PIN_ALERT_RELAY, level >= ALERT_MEDIUM ? HIGH : LOW);

  if (level == ALERT_NONE) {
    Serial.println("[ok] all instant thresholds within range");
  }
  return level;
}

// ----------------------------------------------------------------------------
// Sample sensors. With -DSIMULATE_SENSORS we synthesise plausible, contract-valid
// values (mirroring scripts/esp_emulator.py's normal scenario) so the node runs
// the FULL closed loop with no sensors wired. Without the flag it reads the real
// bus via the shared sensors:: driver.
// ----------------------------------------------------------------------------
static SensorReadings sampleSensors() {
#ifdef SIMULATE_SENSORS
  // Gentle diurnal wiggle so dashboard charts look alive — same idea as the
  // emulator's sin(tick/6) jitter, here driven by the publish counter.
  const float wiggle = sinf(static_cast<float>(g_publishCount) / 6.0f);
  SensorReadings r;
  r.air_temp_c          = 24.0f + 2.0f * wiggle;   // °C, comfortably < AIR_TEMP_VENT
  r.rh_pct              = 64.0f + 3.0f * wiggle;   // %RH, < RH_FUNGAL_WARN
  r.leaf_wetness        = 8.0f;
  r.ppfd                = 600.0f;
  r.co2_ppm             = 450.0f;
  r.soil_moisture_pct   = 42.0f + 3.0f * wiggle;   // %VWC, > SOIL_IRRIGATE_MIN
  r.soil_temp_c         = 22.0f;
  r.npk_n_ppm           = 165;
  r.npk_p_ppm           = 78;
  r.npk_k_ppm           = 215;
  r.water_flow_l_total  = 0.0f;
  r.water_flow_l_per_min = 0.0f;
  r.pheromone_count     = 3;
  r.battery_v           = 3.9f;
  r.rssi                = WiFi.isConnected() ? WiFi.RSSI() : NPK_NA;
  return r;
#else
  SensorReadings r = sensors::sampleAll();
  // On the WiFi node "rssi" reports the WiFi link quality (the LoRa node reports
  // the radio RSSI instead); the backend treats it the same.
  r.rssi = WiFi.isConnected() ? WiFi.RSSI() : NPK_NA;
  return r;
#endif
}

// ----------------------------------------------------------------------------
// Build the telemetry JSON. Field names + types MUST match TelemetryIn
// (app/schemas/telemetry.py). Missing reads become JSON null. ts is epoch
// seconds — a WiFi node has accurate time once it joins the network, but even a
// raw boot-relative value is accepted (TelemetryIn.ts parses epoch s/ms/ISO).
// ----------------------------------------------------------------------------
static String buildTelemetryJson(const SensorReadings &r, AlertLevel localAlert) {
  JsonDocument doc;

  // ---- Identity (device_id is part of the contract; the rest are routing hints
  //      the backend ignores via extra="ignore") ----
  doc["device_id"] = DEVICE_UID;          // == TelemetryIn.device_id
  doc["org_id"]    = ORG_ID;
  doc["fw"]        = FW_VERSION;

  // ---- Timestamp: epoch seconds when NTP/time is set, else millis()/1000. ----
  // The broker topic's device_uid is authoritative for routing; ts is for the
  // reading clock. time(nullptr) returns a real epoch once configTime() lands.
  const time_t now = time(nullptr);
  doc["ts"] = (now > 1600000000) ? static_cast<uint32_t>(now)   // plausible epoch
                                 : (millis() / 1000UL);

  // Floats -> JSON, NAN -> null (2 dp to keep the payload compact + readable).
  auto putF = [&](const char *k, float v) {
    if (isnan(v)) doc[k] = nullptr; else doc[k] = serialized(String(v, 2));
  };
  auto putI = [&](const char *k, int32_t v) {
    if (v == NPK_NA) doc[k] = nullptr; else doc[k] = v;
  };

  // ---- Microclimate ----
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

  // ---- Local instant-alert hint (offline UX; backend re-derives via risk eng) ----
  doc["local_alert"] = static_cast<int>(localAlert);

  String out;
  serializeJson(doc, out);
  return out;
}

// ----------------------------------------------------------------------------
// Drive the vent relay for a verb and return the resulting state string (or
// nullptr for an unknown verb). HIGH=open/on, LOW=closed/off.
// ----------------------------------------------------------------------------
static const char *driveVent(const char *verb) {
  for (const VerbState &vs : VERB_TABLE) {
    if (strcmp(verb, vs.verb) == 0) {
      digitalWrite(PIN_VENT_RELAY, vs.energize ? HIGH : LOW);
      return vs.state;
    }
  }
  return nullptr;  // unknown verb
}

// ----------------------------------------------------------------------------
// Publish the state ack. Shape MUST match what app/control/ingest.py expects:
//   {command_id, actuator_uid, state, ok, ts[, error]}
// (mirrors esp_emulator.py). command_id may be null if the command omitted it;
// the backend then correlates to the most-recent unacked command for the
// actuator. We re-use the command's actuator_uid so the right ActuatorDevice is
// confirmed even if the node ever drives more than one relay.
// ----------------------------------------------------------------------------
static void publishStateAck(const char *command_id, const char *actuator_uid,
                            const char *state, bool ok, const char *error) {
  JsonDocument ack;
  if (command_id) ack["command_id"] = command_id; else ack["command_id"] = nullptr;
  ack["actuator_uid"] = actuator_uid ? actuator_uid : VENT_ACTUATOR_UID;
  ack["state"] = state;
  ack["ok"] = ok;
  if (!ok && error) ack["error"] = error;
  // ISO-ish ts is fine; the backend ingest handler stamps its own now() anyway
  // and does not parse this field. Send epoch seconds for a compact, valid value.
  const time_t now = time(nullptr);
  ack["ts"] = (now > 1600000000) ? static_cast<uint32_t>(now) : (millis() / 1000UL);

  String payload;
  serializeJson(ack, payload);
  // QoS in PubSubClient publish is fire-and-forget (QoS0). The backend consumer
  // subscribes at QoS1; a retained=false QoS0 ack is what the verified loop uses.
  const bool sent = mqtt.publish(TOPIC_STATE.c_str(), payload.c_str());
  Serial.printf("[mqtt] ack -> %s %s ok=%d %s\n", TOPIC_STATE.c_str(),
                state, ok ? 1 : 0, sent ? "" : "(PUBLISH FAILED)");
}

// ----------------------------------------------------------------------------
// MQTT message callback: a command arrived on TOPIC_COMMAND. Parse
//   {command_id, actuator_uid, actuator_type, command, params, ts}
// drive the relay, then publish the state ack — closing the loop.
// ----------------------------------------------------------------------------
static void onMqttMessage(char *topic, byte *payload, unsigned int len) {
  Serial.printf("[mqtt] rx %u bytes on %s\n", len, topic);

  // We only subscribe to the command topic, but guard anyway.
  if (TOPIC_COMMAND != topic) {
    Serial.printf("[mqtt] ignoring unexpected topic %s\n", topic);
    return;
  }

  JsonDocument cmd;
  const DeserializationError err = deserializeJson(cmd, payload, len);
  if (err) {
    Serial.printf("[mqtt] bad command JSON: %s\n", err.c_str());
    // Can't ack a command we couldn't parse (no command_id) — just drop it.
    return;
  }

  // ArduinoJson returns "" for a missing/null string field; normalise the verb.
  const char *command_id  = cmd["command_id"]  | (const char *)nullptr;
  const char *actuator    = cmd["actuator_uid"] | VENT_ACTUATOR_UID;
  String verb = String((const char *)(cmd["command"] | ""));
  verb.toLowerCase();
  verb.trim();

  const char *newState = driveVent(verb.c_str());
  if (newState == nullptr) {
    Serial.printf("[mqtt] !! unknown command verb: '%s'\n", verb.c_str());
    // Ack a failure so the dashboard marks the command FAILED instead of hanging.
    static char errbuf[48];
    snprintf(errbuf, sizeof(errbuf), "unknown verb %s", verb.c_str());
    publishStateAck(command_id, actuator, g_ventState, false, errbuf);
    return;
  }

  g_ventState = newState;
  Serial.printf("[mqtt] >> RELAY '%s' -> vent is now %s (cmd %s)\n",
                verb.c_str(), g_ventState, command_id ? command_id : "(none)");
  // The relay physically flipped — now ack the confirmed state up to the broker.
  publishStateAck(command_id, actuator, g_ventState, true, nullptr);
}

// ----------------------------------------------------------------------------
// WiFi: connect (blocking, bounded) and keep-alive. The WiFi stack auto-reconnects
// in the background; we only need to (re)kick it if it ever drops fully.
// ----------------------------------------------------------------------------
static void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[wifi] connecting to '%s'", WIFI_SSID);

  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000UL) {
    delay(250);
    Serial.print('.');
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[wifi] connected, ip=%s rssi=%d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
    // Set the clock from NTP so telemetry ts carries real wall-clock epoch.
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  } else {
    Serial.println("\n[wifi] connect timed out — will retry in loop()");
  }
}

// ----------------------------------------------------------------------------
// MQTT: (re)connect with exponential-ish backoff and (re)subscribe to commands.
// Returns true once connected. Non-blocking-friendly: tries ONE connect per call
// so loop() keeps servicing the network; the caller throttles retries.
// ----------------------------------------------------------------------------
static bool connectMqtt() {
  if (mqtt.connected()) return true;
  if (WiFi.status() != WL_CONNECTED) return false;  // need the link first

  // Stable, unique client id so the broker's session/LWT is per-device.
  const String clientId = String("angawatch-") + DEVICE_UID;
  Serial.printf("[mqtt] connecting to %s:%d as %s ...\n", MQTT_HOST, (int)MQTT_PORT, clientId.c_str());

  // Last-will: if this node drops off ungracefully, the broker publishes an
  // offline marker to the state topic so the dashboard can flag the node down.
  // (Optional — the backend tolerates its absence; kept for operational clarity.)
  const bool ok = (strlen(MQTT_USER) > 0)
      ? mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASS)
      : mqtt.connect(clientId.c_str());

  if (ok) {
    mqtt.subscribe(TOPIC_COMMAND.c_str(), 1);  // QoS1 so commands aren't dropped
    Serial.printf("[mqtt] connected\n[mqtt]   telemetry -> %s\n[mqtt]   commands  <- %s\n",
                  TOPIC_TELEMETRY.c_str(), TOPIC_COMMAND.c_str());
    return true;
  }
  Serial.printf("[mqtt] connect failed, state=%d (retrying)\n", mqtt.state());
  return false;
}

// ----------------------------------------------------------------------------
// Sample + threshold + publish one telemetry message.
// ----------------------------------------------------------------------------
static void publishTelemetry() {
  const SensorReadings r = sampleSensors();
  const AlertLevel localAlert = evaluateThresholds(r);  // drives PIN_ALERT_RELAY
  const String payload = buildTelemetryJson(r, localAlert);

  const bool sent = mqtt.publish(TOPIC_TELEMETRY.c_str(), payload.c_str());
  Serial.printf("[mqtt] telemetry t=%.1fC rh=%.1f%% vent=%s -> %s %s\n",
                r.air_temp_c, r.rh_pct, g_ventState, TOPIC_TELEMETRY.c_str(),
                sent ? "" : "(PUBLISH FAILED)");
  g_publishCount++;
}

// ----------------------------------------------------------------------------
// setup(): Serial, sensors, relay pins, WiFi, MQTT, (optional) OTA.
// ----------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(50);
  Serial.printf("\n=== AngaWatch WiFi+MQTT node %s (org %s) fw %s ===\n",
                DEVICE_UID, ORG_ID, FW_VERSION);
#ifdef SIMULATE_SENSORS
  Serial.println("[cfg] SIMULATE_SENSORS=1 — synthesising readings (no sensors needed)");
#endif

  // Vent relay starts de-energized (closed); init BEFORE anything can command it.
  pinMode(PIN_VENT_RELAY, OUTPUT);
  digitalWrite(PIN_VENT_RELAY, LOW);
  g_ventState = "closed";

  // Local alert relay/buzzer (sensors::begin also sets this, but the WiFi node
  // may run with SIMULATE_SENSORS and never call the real driver — set it here).
  pinMode(PIN_ALERT_RELAY, OUTPUT);
  digitalWrite(PIN_ALERT_RELAY, LOW);

#ifndef SIMULATE_SENSORS
  sensors::begin();
#endif

  connectWiFi();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);
  // Telemetry doc is ~400 B; PubSubClient's 256 B default would silently drop it.
  mqtt.setBufferSize(768);
  mqtt.setKeepAlive(30);
  connectMqtt();

#if OTA_ENABLED
  // The WiFi node is already on the network, so OTA stays available here (unlike
  // the LoRa node which only gets an OTA window if separately WiFi-equipped).
  ArduinoOTA.setHostname(OTA_HOSTNAME);
  // ArduinoOTA.setPassword(...);  // set via secrets/build flag in production
  ArduinoOTA.begin();
  Serial.printf("[ota] ready as %s\n", OTA_HOSTNAME);
#endif

  g_nextTelemetryMs = millis();  // publish on the first loop iteration
}

// ----------------------------------------------------------------------------
// loop(): keep MQTT serviced (so commands arrive promptly) and publish telemetry
// on the interval. No deep sleep — the node must stay subscribed for commands.
// ----------------------------------------------------------------------------
void loop() {
  // --- Keep the link + broker session alive (throttled reconnect) ---
  static uint32_t lastReconnectMs = 0;
  if (WiFi.status() != WL_CONNECTED) {
    // Background auto-reconnect is on; nudge it if it's been down a while.
    if (millis() - lastReconnectMs > 5000UL) {
      lastReconnectMs = millis();
      Serial.println("[wifi] link down — reconnecting");
      WiFi.reconnect();
    }
  } else if (!mqtt.connected()) {
    if (millis() - lastReconnectMs > 2000UL) {  // backoff between MQTT retries
      lastReconnectMs = millis();
      connectMqtt();
    }
  } else {
    mqtt.loop();  // service inbound commands + keepalive PINGs
  }

#if OTA_ENABLED
  ArduinoOTA.handle();
#endif

  // --- Publish telemetry on the interval (only when we can actually send) ---
  if (mqtt.connected() && (int32_t)(millis() - g_nextTelemetryMs) >= 0) {
    g_nextTelemetryMs = millis() + TELEMETRY_INTERVAL_S * 1000UL;
    publishTelemetry();
  }

  delay(10);  // yield to the WiFi/MQTT stacks; keeps the watchdog happy
}
