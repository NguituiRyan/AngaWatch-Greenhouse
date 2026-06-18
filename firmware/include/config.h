// ============================================================================
// config.h — board / pin / radio / identity configuration for one AngaWatch node
// ----------------------------------------------------------------------------
// Everything that changes per board, per region, or per deployment lives here so
// the rest of the firmware stays portable. Pin numbers are GPIO numbers for a
// generic ESP32 dev module wired to an SX1276/RFM95 LoRa breakout plus the
// greenhouse sensor bus. RECALIBRATE for your exact board — see README.md.
// ============================================================================

#ifndef ANGAWATCH_CONFIG_H
#define ANGAWATCH_CONFIG_H

#include <Arduino.h>

// ----------------------------------------------------------------------------
// Node identity. These map directly onto the backend telemetry contract:
//   MQTT topic = farm/{ORG_ID}/{DEVICE_UID}/telemetry
//   TelemetryIn.device_id == DEVICE_UID
// The gateway reads ORG_ID + DEVICE_UID out of the LoRa JSON to build the topic,
// so they MUST match the seeded Device.device_uid / Organization in the backend.
// Demo defaults mirror app/seed/constants.py (org "demo-coop", device GH1-NODE-01).
// ----------------------------------------------------------------------------
#define DEVICE_UID   "GH1-NODE-01"   // unique node id; == Device.device_uid
#define ORG_ID       "demo-coop"     // owning organization slug/id
#define GREENHOUSE   "GH-1"          // human label, informational only
#define FW_VERSION   "0.1.0"         // bumped on every OTA release

// ----------------------------------------------------------------------------
// Deep-sleep cadence. The node spends almost all of its life asleep to stretch
// a small solar/battery budget. 15 min between readings is plenty for a slow
// microclimate; drop it during a blight/heat event if you add adaptive cadence.
// ----------------------------------------------------------------------------
#define DEEP_SLEEP_MINUTES        15ULL
#define uS_PER_MINUTE             (60ULL * 1000000ULL)
#define DEEP_SLEEP_INTERVAL_US    (DEEP_SLEEP_MINUTES * uS_PER_MINUTE)

// Safety watchdog: if a single wake cycle (read + transmit) runs longer than
// this, force deep sleep anyway so a stuck sensor can never drain the battery.
#define MAX_AWAKE_MS              20000UL

// ----------------------------------------------------------------------------
// LoRa radio (SX1276 / RFM95) — SPI + control pins.
// Defaults follow the common TTGO/Heltec LoRa32 pinout. Verify against your
// board silkscreen; a wrong DIO0/RST pin is the #1 "radio won't init" cause.
// ----------------------------------------------------------------------------
#define LORA_FREQUENCY     868E6   // EU868 ISM band (Hz). See platformio.ini.
#define LORA_TX_POWER_DBM  17      // 2..20 dBm; higher = more range, more drain.
#define LORA_SPREADING     9       // SF7..SF12; higher = more range, lower rate.
#define LORA_BANDWIDTH     125E3   // Hz
#define LORA_CODING_RATE   5       // 4/5 .. 4/8  -> pass 5..8
#define LORA_SYNC_WORD     0x12    // private network sync word (avoid 0x34 LoRaWAN)
#define LORA_PREAMBLE_LEN  8

#define PIN_LORA_SCK       5
#define PIN_LORA_MISO      19
#define PIN_LORA_MOSI      27
#define PIN_LORA_SS        18      // NSS / chip select
#define PIN_LORA_RST       14      // radio reset
#define PIN_LORA_DIO0      26      // TX/RX done IRQ

// ----------------------------------------------------------------------------
// Sensor bus pins.
// ----------------------------------------------------------------------------
// I2C (SHT4x air temp/RH, optional CO2/PPFD digital sensors).
#define PIN_I2C_SDA        21
#define PIN_I2C_SCL        22

// DS18B20 soil temperature (OneWire).
#define PIN_SOIL_TEMP_DQ   4

// Capacitive soil-moisture probe (analog). ADC1 channel survives deep sleep.
#define PIN_SOIL_MOISTURE  34      // ADC1_CH6, input-only
// Calibration: raw ADC counts in fully dry air vs. submerged in water. These
// MUST be measured per probe (see README "Calibration"); placeholders below.
#define SOIL_ADC_DRY       3000    // ~0 % VWC
#define SOIL_ADC_WET       1200    // ~100 % VWC

// Leaf-wetness grid sensor (analog). High resistance = dry, low = wet film.
#define PIN_LEAF_WETNESS   35      // ADC1_CH7, input-only
#define LEAF_ADC_DRY       3200
#define LEAF_ADC_WET       900

// PPFD / light (analog quantum sensor or LDR proxy). Swap for an I2C lux sensor
// + conversion factor for accuracy.
#define PIN_PPFD           32      // ADC1_CH4
#define PPFD_ADC_FULLSCALE 4095.0f
#define PPFD_MAX_UMOL      2000.0f // µmol·m⁻²·s⁻¹ at full-scale ADC

// RS485 / Modbus-RTU NPK soil sensor (UART2 + MAX485 direction pin).
#define PIN_RS485_RX       16      // ESP32 RX2  <- RO  (MAX485)
#define PIN_RS485_TX       17      // ESP32 TX2  -> DI  (MAX485)
#define PIN_RS485_DE       33      // DE+RE tied together; HIGH=transmit
#define NPK_MODBUS_ADDR    0x01    // sensor slave address
#define NPK_BAUD           9600

// Pheromone trap counter: reed/IR beam-break on an interrupt-capable RTC GPIO so
// catches are counted even while the MCU deep-sleeps (ext1 wake / pulse latch).
#define PIN_PHEROMONE_TRAP 25      // RTC-capable GPIO

// Battery voltage via resistor divider on an ADC pin. Divider ratio converts the
// measured node voltage back to pack voltage (e.g. 2:1 divider -> ratio 2.0).
#define PIN_BATTERY_ADC    39      // ADC1_CH3, input-only
#define BATTERY_DIVIDER    2.0f
#define ADC_REF_VOLTS      3.30f
#define ADC_MAX_COUNTS     4095.0f

// ----------------------------------------------------------------------------
// Local-alert actuator: relay/buzzer the node can trip WITHOUT the cloud when an
// instant threshold (see thresholds.h) is breached. This is the offline safety
// net — a farmer hears/sees the alert even with no LoRa coverage.
// ----------------------------------------------------------------------------
#define PIN_ALERT_RELAY    13      // drives vent relay / buzzer; active HIGH

// ----------------------------------------------------------------------------
// OTA (optional, when the node has WiFi backhaul instead of LoRa-only).
// Credentials are compile-time placeholders; prefer ArduinoOTA password / signed
// updates in production. Hooks live in src/main.cpp.
// ----------------------------------------------------------------------------
#define OTA_ENABLED        0        // 0 = LoRa-only node; 1 = WiFi+OTA node
#define OTA_HOSTNAME       "angawatch-" DEVICE_UID
#define WIFI_SSID          ""       // set when OTA_ENABLED
#define WIFI_PASSWORD      ""

#endif  // ANGAWATCH_CONFIG_H
