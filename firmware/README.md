# AngaWatch Greenhouse — ESP32 LoRa Sensor Node Firmware

PlatformIO firmware for the in-greenhouse sensor node. Each node wakes on an RTC
timer, reads the greenhouse sensor bus, runs the **instant microclimate threshold
rules locally** (so a farmer still gets a relay/buzzer alert when the network is
down), encodes a telemetry JSON packet, transmits it over **868 MHz LoRa** to the
field gateway, and returns to deep sleep.

The gateway validates each packet against `app/schemas/telemetry.py` (`TelemetryIn`)
and republishes it to MQTT topic `farm/{org_id}/{device_id}/telemetry`, where the
backend ingestion consumer persists it.

> This project is authored for clarity and is **not compiled in CI**. Pin maps and
> calibration constants are sane defaults — verify against your exact hardware
> before flashing.

---

## Project layout

```
firmware/
├── platformio.ini        # env esp32dev, libs, deep-sleep build flags
├── include/
│   ├── config.h          # pins, LoRa params, identity, deep-sleep interval
│   └── thresholds.h      # instant microclimate thresholds (mirror backend)
├── src/
│   ├── main.cpp          # RTC/deep-sleep flow: read → threshold → JSON → TX → sleep
│   ├── sensors.h/.cpp    # SHT4x, soil moisture/temp, RS485 NPK, leaf wetness,
│   │                     # PPFD, pheromone trap, battery ADC
│   └── lora.h/.cpp       # SX1276/RFM95 init + send
└── README.md
```

---

## Hardware / wiring

Target board: generic **ESP32 dev module** + **SX1276/RFM95 (868 MHz)** LoRa radio.
All pins below are GPIO numbers and live in `include/config.h`.

### LoRa radio (SPI)

| SX1276 pin | ESP32 GPIO | `config.h`        |
|------------|-----------|-------------------|
| SCK        | 5         | `PIN_LORA_SCK`    |
| MISO       | 19        | `PIN_LORA_MISO`   |
| MOSI       | 27        | `PIN_LORA_MOSI`   |
| NSS / CS   | 18        | `PIN_LORA_SS`     |
| RST        | 14        | `PIN_LORA_RST`    |
| DIO0       | 26        | `PIN_LORA_DIO0`   |
| VCC / GND  | 3V3 / GND | —                 |

> On integrated boards (TTGO/Heltec LoRa32) these are already routed — match the
> defaults to your board's pinout; a wrong DIO0/RST is the #1 "radio won't init"
> cause.

### Sensors

| Sensor                         | Interface | ESP32 GPIO            | `config.h`            |
|--------------------------------|-----------|-----------------------|-----------------------|
| SHT4x air temp + RH            | I2C       | SDA 21 / SCL 22       | `PIN_I2C_SDA/SCL`     |
| DS18B20 soil temp              | OneWire   | 4 (+4.7 kΩ pull-up)   | `PIN_SOIL_TEMP_DQ`    |
| Capacitive soil moisture       | analog    | 34 (ADC1)             | `PIN_SOIL_MOISTURE`   |
| Leaf-wetness grid              | analog    | 35 (ADC1)             | `PIN_LEAF_WETNESS`    |
| PPFD / quantum light           | analog    | 32 (ADC1)             | `PIN_PPFD`            |
| RS485 NPK (7-in-1)             | Modbus-RTU| RX2 16 / TX2 17 / DE 33 | `PIN_RS485_*`       |
| Pheromone trap (beam-break)    | digital   | 25 (RTC GPIO)         | `PIN_PHEROMONE_TRAP`  |
| Battery voltage                | analog    | 39 (ADC1, divider)    | `PIN_BATTERY_ADC`     |
| Local alert relay / buzzer     | digital   | 13                    | `PIN_ALERT_RELAY`     |

**RS485 note:** the NPK probe needs a half-duplex transceiver (MAX485/SP3485).
Tie DE+RE together to `PIN_RS485_DE` (HIGH = transmit). Use ADC1 pins (GPIO 32–39)
for all analog sensors — ADC2 is unavailable while WiFi/radio is active and does
not survive deep sleep.

**Power:** a Li-ion/LiFePO₄ pack + small solar panel suits the ~15-minute duty
cycle. The node sleeps at micro-amp current between reads; size the panel for the
TX burst plus sensor warm-up.

---

## Build & flash

Install [PlatformIO](https://platformio.org/) (CLI or VS Code extension), then
from the `firmware/` directory:

```bash
# Build
pio run -e esp32dev

# Flash over USB (auto-detects the serial port)
pio run -e esp32dev -t upload

# Open the serial monitor (115200 baud) to watch a wake cycle
pio device monitor -b 115200
```

A healthy cycle prints the boot banner, each fired threshold, the telemetry JSON,
`[lora] packet sent`, then `[sleep] deep sleep for 15 min`.

---

## OTA (over-the-air) updates

OTA is **stubbed and disabled by default** because the standard node is LoRa-only
(no IP backhaul). For a WiFi-equipped node:

1. Set `OTA_ENABLED 1` and fill `WIFI_SSID` / `WIFI_PASSWORD` in `config.h`.
2. The node brings up WiFi + `ArduinoOTA` in `setup()` (see the `OTA-READY` hooks
   in `src/main.cpp`) and exposes an update window before sleeping.
3. Flash over the air with the `esp32dev_ota` env:

   ```bash
   pio run -e esp32dev_ota -t upload --upload-port <node-ip>
   ```

In production, set an OTA password (or signed updates) and keep the awake/update
window short so a WiFi node still hits its power budget.

---

## Calibration

The defaults in `config.h` are placeholders — **measure per probe**:

- **Soil moisture** (`SOIL_ADC_DRY` / `SOIL_ADC_WET`): record the raw ADC count
  with the probe in dry air, then submerged to the line in water. Put dry → `_DRY`,
  wet → `_WET`. `adcToPercent()` maps everything in between to 0–100 % VWC.
- **Leaf wetness** (`LEAF_ADC_DRY` / `LEAF_ADC_WET`): dry grid vs. fully wetted grid.
- **PPFD** (`PPFD_MAX_UMOL`): scale full-scale ADC to your quantum sensor's µmol
  range, or swap in a calibrated I2C lux sensor and a lux→PPFD factor.
- **Battery** (`BATTERY_DIVIDER`): set to your resistor-divider ratio; trim against
  a multimeter reading of the pack.
- **NPK registers** (`NPK_REG_START` in `sensors.cpp`): register map varies by
  vendor — confirm N/P/K register addresses and scaling against the datasheet.

### Thresholds

`include/thresholds.h` mirrors the backend **microclimate** risk model and is the
node's offline safety net:

| Constant            | Value | Action                          |
|---------------------|-------|---------------------------------|
| `AIR_TEMP_VENT`     | 35 °C | vent now (HIGH)                 |
| `RH_FUNGAL_WARN`    | 85 %  | fungal-pressure warning (MEDIUM)|
| `SOIL_IRRIGATE_MIN` | 25 %  | irrigate (MEDIUM)               |
| `SOIL_IRRIGATE_CRIT`| 15 %  | irrigate, critical (HIGH)       |

Keep these in sync with the backend `RiskModelConfig` defaults if you re-tune them
in the field. The cloud risk engine remains the source of truth for the windowed
and forecast-fused models (late blight, *Tuta absoluta*); the node only
re-implements the **instant** rules for offline alerting.
