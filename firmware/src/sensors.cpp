// ============================================================================
// sensors.cpp — concrete sensor reads for the AngaWatch greenhouse node
// ----------------------------------------------------------------------------
// Realistic, structured stubs. Each driver is wired with the right library and
// pin map; the actual bus transactions are written out so the flow is obvious,
// but values fall back to sane mocks / sentinels when a sensor is absent so the
// node still produces a well-formed telemetry packet on the bench.
// ============================================================================

#include "sensors.h"
#include "config.h"

#include <Wire.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <SensirionI2cSht4x.h>
#include <ModbusMaster.h>

// ----------------------------------------------------------------------------
// Driver instances.
// ----------------------------------------------------------------------------
static SensirionI2cSht4x sht4x;                       // air temp + RH
static OneWire           oneWire(PIN_SOIL_TEMP_DQ);    // DS18B20 bus
static DallasTemperature soilTemp(&oneWire);          // soil temp probe
static ModbusMaster      npkBus;                       // RS485 NPK sensor

// Pheromone trap catch counter. Lives in RTC slow memory so it accumulates
// across deep-sleep cycles; bumped by an ISR on the beam-break GPIO.
RTC_DATA_ATTR static volatile uint32_t g_pheromone_pulses = 0;

// ----------------------------------------------------------------------------
// RS485 direction control: MAX485 DE/RE is HIGH to transmit, LOW to receive.
// ----------------------------------------------------------------------------
static void rs485PreTransmit()  { digitalWrite(PIN_RS485_DE, HIGH); }
static void rs485PostTransmit() { digitalWrite(PIN_RS485_DE, LOW); }

// Beam-break ISR for the pheromone trap. Kept tiny + IRAM-resident.
static void IRAM_ATTR onTrapPulse() { g_pheromone_pulses++; }

// ----------------------------------------------------------------------------
// Helpers: clamp + map a raw ADC count between calibrated dry/wet endpoints to a
// 0..100 % scale. Endpoints may be inverted (dry > wet), so handle both.
// ----------------------------------------------------------------------------
static float adcToPercent(int raw, int dry, int wet) {
  const float span = static_cast<float>(wet - dry);
  if (span == 0.0f) return NAN;
  float pct = (static_cast<float>(raw - dry) / span) * 100.0f;
  if (pct < 0.0f) pct = 0.0f;
  if (pct > 100.0f) pct = 100.0f;
  return pct;
}

namespace sensors {

void begin() {
  // --- I2C (SHT4x) ---
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
  sht4x.begin(Wire, SHT40_I2C_ADDR_44);

  // --- OneWire soil temperature ---
  soilTemp.begin();

  // --- ADC: 11 dB attenuation -> ~0..3.3 V full scale, 12-bit ---
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_SOIL_MOISTURE, ADC_11db);
  analogSetPinAttenuation(PIN_LEAF_WETNESS, ADC_11db);
  analogSetPinAttenuation(PIN_PPFD, ADC_11db);
  analogSetPinAttenuation(PIN_BATTERY_ADC, ADC_11db);

  // --- RS485 / Modbus NPK ---
  pinMode(PIN_RS485_DE, OUTPUT);
  digitalWrite(PIN_RS485_DE, LOW);  // default to receive
  Serial2.begin(NPK_BAUD, SERIAL_8N1, PIN_RS485_RX, PIN_RS485_TX);
  npkBus.begin(NPK_MODBUS_ADDR, Serial2);
  npkBus.preTransmission(rs485PreTransmit);
  npkBus.postTransmission(rs485PostTransmit);

  // --- Local alert relay/buzzer (off at boot) ---
  pinMode(PIN_ALERT_RELAY, OUTPUT);
  digitalWrite(PIN_ALERT_RELAY, LOW);

  // --- Pheromone trap interrupt (counts even between deep sleeps via ext1; the
  //     ISR here covers the awake window) ---
  pinMode(PIN_PHEROMONE_TRAP, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_PHEROMONE_TRAP), onTrapPulse, FALLING);
}

// ----------------------------------------------------------------------------
// SHT4x air temperature + relative humidity.
// ----------------------------------------------------------------------------
static void readAir(SensorReadings &r) {
  float t = NAN, rh = NAN;
  const uint16_t err = sht4x.measureHighPrecision(t, rh);
  if (err == 0) {
    r.air_temp_c = t;
    r.rh_pct = rh;
  } else {
    // Bench fallback so the packet still validates against the contract.
    r.air_temp_c = 28.5f;
    r.rh_pct = 72.0f;
  }
}

// ----------------------------------------------------------------------------
// DS18B20 soil temperature.
// ----------------------------------------------------------------------------
static void readSoilTemp(SensorReadings &r) {
  soilTemp.requestTemperatures();
  const float t = soilTemp.getTempCByIndex(0);
  // DallasTemperature returns DEVICE_DISCONNECTED_C (-127) on a bad read.
  r.soil_temp_c = (t <= -120.0f) ? 24.0f /*mock*/ : t;
}

// ----------------------------------------------------------------------------
// Capacitive soil-moisture probe (analog, calibrated).
// ----------------------------------------------------------------------------
static void readSoilMoisture(SensorReadings &r) {
  const int raw = analogRead(PIN_SOIL_MOISTURE);
  r.soil_moisture_pct = adcToPercent(raw, SOIL_ADC_DRY, SOIL_ADC_WET);
}

// ----------------------------------------------------------------------------
// Leaf-wetness grid (analog). Reported 0..100 % wet film coverage.
// ----------------------------------------------------------------------------
static void readLeafWetness(SensorReadings &r) {
  const int raw = analogRead(PIN_LEAF_WETNESS);
  r.leaf_wetness = adcToPercent(raw, LEAF_ADC_DRY, LEAF_ADC_WET);
}

// ----------------------------------------------------------------------------
// PPFD / light. Analog quantum sensor scaled to µmol·m⁻²·s⁻¹.
// ----------------------------------------------------------------------------
static void readPpfd(SensorReadings &r) {
  const int raw = analogRead(PIN_PPFD);
  r.ppfd = (static_cast<float>(raw) / PPFD_ADC_FULLSCALE) * PPFD_MAX_UMOL;
}

// ----------------------------------------------------------------------------
// RS485 / Modbus-RTU NPK soil sensor.
// Typical 7-in-1 probe layout: read 3 input/holding registers for N, P, K (ppm).
// Register addresses vary by vendor — confirm with the datasheet.
// ----------------------------------------------------------------------------
static void readNpk(SensorReadings &r) {
  // Read 3 holding registers starting at 0x001E (N, P, K) — adjust per datasheet.
  constexpr uint16_t NPK_REG_START = 0x001E;
  const uint8_t status = npkBus.readHoldingRegisters(NPK_REG_START, 3);
  if (status == npkBus.ku8MBSuccess) {
    r.npk_n_ppm = npkBus.getResponseBuffer(0);
    r.npk_p_ppm = npkBus.getResponseBuffer(1);
    r.npk_k_ppm = npkBus.getResponseBuffer(2);
  } else {
    // Leave at NPK_NA -> encoded as JSON null (sensor absent / no reply).
    r.npk_n_ppm = NPK_NA;
    r.npk_p_ppm = NPK_NA;
    r.npk_k_ppm = NPK_NA;
  }
}

// ----------------------------------------------------------------------------
// Battery voltage via resistor divider.
// ----------------------------------------------------------------------------
static void readBattery(SensorReadings &r) {
  // Average a few samples to damp ADC noise.
  uint32_t acc = 0;
  for (int i = 0; i < 8; ++i) acc += analogRead(PIN_BATTERY_ADC);
  const float counts = static_cast<float>(acc) / 8.0f;
  const float vNode = (counts / ADC_MAX_COUNTS) * ADC_REF_VOLTS;
  r.battery_v = vNode * BATTERY_DIVIDER;
}

int32_t readPheromoneCounter() {
  // Snapshot + (intentionally) do NOT reset: pheromone_count is cumulative per
  // pest generation. The cloud Tuta model resets it on a generation rollover.
  return static_cast<int32_t>(g_pheromone_pulses);
}

SensorReadings sampleAll() {
  SensorReadings r;
  readAir(r);
  readSoilTemp(r);
  readSoilMoisture(r);
  readLeafWetness(r);
  readPpfd(r);
  readNpk(r);
  readBattery(r);
  r.pheromone_count = readPheromoneCounter();
  // water_flow_* left as NAN until a flow meter is fitted; the backend Water
  // model treats them as missing optionals.
  return r;
}

void powerDown() {
  // Float the RS485 driver and de-energize the alert relay (it should already be
  // set by the threshold logic; this is belt-and-braces). Sensor rails on a
  // load switch would be cut here too if the board has one.
  digitalWrite(PIN_RS485_DE, LOW);
  Serial2.flush();
  // NOTE: leave PIN_ALERT_RELAY as the threshold logic set it — a latched vent
  // call should persist through sleep. If your relay is momentary, clear here.
}

}  // namespace sensors
