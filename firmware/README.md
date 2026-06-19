# AngaWatch Greenhouse — ESP32 Node Firmware

PlatformIO firmware for the in-greenhouse node. It reads the greenhouse sensor
bus, runs the **instant microclimate threshold rules locally** (so a farmer still
gets a relay/buzzer alert when the network is down), encodes a telemetry JSON
packet matching `app/schemas/telemetry.py` (`TelemetryIn`), and ships it to the
backend over one of **two backhauls** you pick at build time.

> This project is authored for clarity and is **not compiled in CI**. Pin maps and
> calibration constants are sane defaults — verify against your exact hardware
> before flashing.

---

## Two backhauls — pick per node

| | **LoRa node** (`esp32dev`) | **WiFi+MQTT node** (`esp32-wifi`) |
|---|---|---|
| Source | `src/main.cpp` | `src/main_wifi.cpp` |
| Transport | 868 MHz LoRa → field gateway → MQTT | WiFi → **MQTT broker directly** |
| Range / siting | km-scale, off-grid field | within WiFi/AP coverage |
| Power | **deep sleep** ~15 min; µA between reads → tiny solar/battery | **always awake** → mains or solar-buffered pack |
| Telemetry up | ✅ (gateway republishes) | ✅ (publishes itself) |
| **Commands down + state ack** | ❌ (asleep, TX-only) | ✅ **closes the loop with the dashboard** |
| OTA | only if separately WiFi-equipped | ✅ already on the network |

**LoRa node** — wakes on an RTC timer, samples, transmits one LoRa packet to the
field gateway, returns to deep sleep. The gateway validates the packet and
republishes it to `farm/{org_id}/{device_id}/telemetry`. It cannot receive vent
commands because it is asleep almost all the time.

**WiFi+MQTT node** — stays awake and talks **directly** to the same MQTT broker the
backend and dashboard use. It publishes telemetry, **subscribes to commands**, and
**publishes a state ack** after it flips the vent relay — so the dashboard's
open/close button drives real hardware and reflects the confirmed state. This is
the node that **closes the control loop**.

> **Why awake?** To receive a command the instant the dashboard sends it, the WiFi
> node must stay subscribed — it cannot deep-sleep. That continuous WiFi/MQTT draw
> (tens of mA) is the trade-off for closed-loop control: power it from mains or a
> solar-buffered pack. The LoRa node trades control for a multi-month battery.

The two paths are independent: building one never breaks the other (the PlatformIO
`build_src_filter`s keep `main.cpp` and `main_wifi.cpp` from colliding).

---

## The MQTT contract (verified)

The WiFi node speaks the backend's **fixed, live-verified** topic contract. It
mirrors `scripts/esp_emulator.py` byte-for-byte, which the loop verifier
(`scripts/verify_loop.py`) passes.

**Telemetry UP** → `farm/{ORG_ID}/{DEVICE_UID}/telemetry`
Payload = the `TelemetryIn` JSON (`device_id`, `ts`, `air_temp_c`, `rh_pct`,
`leaf_wetness`, `soil_moisture_pct`, `soil_temp_c`, `ppfd`, optional `co2_ppm`,
`npk_*`, `water_flow_*`, `pheromone_count`, `battery_v`, `rssi`). Missing sensors
are sent as JSON `null`.

**Command DOWN** → `farm/{ORG_ID}/{DEVICE_UID}/command` (subscribed)
Payload = `{command_id, actuator_uid, actuator_type, command, params, ts}`, where
`command` ∈ `open | close | on | off`.

**State / ack UP** → `farm/{ORG_ID}/{DEVICE_UID}/state` (published after the relay flips)
Payload = `{command_id, actuator_uid, state, ok, ts}`. The backend consumer
(`app/control/ingest.py`) turns this into the confirmed `ActuatorDevice.state` plus
an `ACKED` `ControlCommand` — that is what makes the dashboard reflect reality.

Verb → relay → state mapping (matches the backend + emulator):

| `command` | `PIN_VENT_RELAY` | reported `state` |
|-----------|------------------|------------------|
| `open` / `on` | HIGH | `open` / `on` |
| `close` / `off` | LOW | `closed` / `off` |
| anything else | unchanged | `ok:false`, `error:"unknown verb …"` |

> ⚠️ **`ORG_ID` must be the Organization UUID for the WiFi node**, not the
> `demo-coop` slug — the backend consumer parses `{org_id}` from the topic as a
> UUID (`app/ingestion/consumer.py`). The LoRa path can use the slug because the
> gateway resolves it to a UUID before publishing.

---

## Project layout

```
firmware/
├── platformio.ini            # envs: esp32dev (LoRa) + esp32-wifi (WiFi+MQTT)
├── include/
│   ├── config.h              # pins, LoRa params, identity, vent relay, intervals
│   ├── thresholds.h          # instant microclimate thresholds (mirror backend)
│   ├── secrets.h.example      # WiFi/MQTT creds template -> copy to secrets.h
│   └── secrets.h             # (gitignored) your real creds — NOT committed
├── src/
│   ├── main.cpp              # LoRa node: read → threshold → JSON → LoRa TX → deep sleep
│   ├── main_wifi.cpp         # WiFi node: read/threshold/publish + command → relay → ack
│   ├── sensors.h/.cpp        # SHT4x, soil moisture/temp, RS485 NPK, leaf wetness,
│   │                         # PPFD, pheromone trap, battery ADC  (shared)
│   └── lora.h/.cpp           # SX1276/RFM95 init + send  (LoRa node only)
└── README.md
```

---

## Hardware / wiring

Target board: generic **ESP32 dev module** + **SX1276/RFM95 (868 MHz)** LoRa radio.
All pins below are GPIO numbers and live in `include/config.h`.

### LoRa radio (SPI) — **LoRa node only**

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
> cause. The WiFi node does not use the radio.

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
| **Vent relay (cloud-commanded)** | digital | **12**                | **`PIN_VENT_RELAY`**  |

**Vent relay (WiFi node):** wire a relay/SSR module's IN to `PIN_VENT_RELAY`
(GPIO 12), its COM/NO contacts to the vent motor or actuator, and share grounds.
The firmware drives it **HIGH = open, LOW = closed** on a dashboard command and
acks the new state back to the broker. It is separate from `PIN_ALERT_RELAY` (the
local buzzer/siren the threshold rules trip) so both can act independently. On the
LoRa node `PIN_VENT_RELAY` is simply unused (no command backhaul).

**RS485 note:** the NPK probe needs a half-duplex transceiver (MAX485/SP3485).
Tie DE+RE together to `PIN_RS485_DE` (HIGH = transmit). Use ADC1 pins (GPIO 32–39)
for all analog sensors — ADC2 is unavailable while WiFi/radio is active and does
not survive deep sleep. (The WiFi node uses WiFi, so keep analog sensors on ADC1.)

**Power:**
- *LoRa node* — a Li-ion/LiFePO₄ pack + small solar panel suits the ~15-minute
  duty cycle; it sleeps at micro-amp current between reads.
- *WiFi node* — stays awake to receive commands (tens of mA continuous), so give
  it mains power or a solar-buffered pack with a healthy battery.

---

## Configure secrets (WiFi node)

The WiFi node needs WiFi + broker credentials and the org/device identity. These
live in `include/secrets.h`, which is **gitignored** — never commit real creds.

```bash
# from firmware/
cp include/secrets.h.example include/secrets.h     # Linux/macOS
copy include\secrets.h.example include\secrets.h    # Windows cmd
```

Then edit `include/secrets.h`:

| Define | What |
|--------|------|
| `WIFI_SSID`, `WIFI_PASSWORD` | your access point |
| `MQTT_HOST`, `MQTT_PORT` | the **same broker** the backend/dashboard use (`1883` plain) |
| `MQTT_USER`, `MQTT_PASS` | broker auth (`""` for none) |
| `ORG_ID` | **the Organization UUID** (not the `demo-coop` slug — see contract note above) |
| `DEVICE_UID` | the relay-bearing node uid (default `GH1-NODE-01`) |
| `VENT_ACTUATOR_UID` | the vent actuator uid (default `GH1-VENT-01`) |
| `PIN_VENT_RELAY` | vent relay GPIO (default `12`) |

`config.h` includes `secrets.h` automatically (via `__has_include`) and these
values override the defaults. The LoRa node does **not** need `secrets.h`.

---

## Build & flash

Install [PlatformIO](https://platformio.org/) (CLI or VS Code extension), then run
from the `firmware/` directory.

### LoRa node (`esp32dev`)

```bash
pio run -e esp32dev                 # build
pio run -e esp32dev -t upload       # flash over USB
pio device monitor -b 115200        # watch a wake cycle
```

A healthy cycle prints the boot banner, each fired threshold, the telemetry JSON,
`[lora] packet sent`, then `[sleep] deep sleep for 15 min`.

### WiFi+MQTT node (`esp32-wifi`)

```bash
# after copying/filling include/secrets.h:
pio run -e esp32-wifi               # build
pio run -e esp32-wifi -t upload     # flash over USB
pio device monitor -b 115200        # watch telemetry + commands
```

A healthy node prints `[wifi] connected …`, `[mqtt] connected`, then a
`[mqtt] telemetry …` line every interval. Issue an open from the dashboard and you
will see `[mqtt] >> RELAY 'open' -> vent is now open` followed by
`[mqtt] ack -> …/state open ok=1` — the loop is closed.

**No sensors wired?** Add `-DSIMULATE_SENSORS` (uncomment it in the `[env:esp32-wifi]`
`build_flags`, or `pio run -e esp32-wifi --build-flag="-DSIMULATE_SENSORS"`) and the
node synthesises plausible, contract-valid telemetry — the same values
`scripts/esp_emulator.py` produces — so you can exercise the full closed loop with
just a bare board.

> **Tip:** before touching hardware, prove the broker + backend loop with the pure
> Python stand-in: `python scripts/esp_emulator.py --org-id <ORG_UUID> --uid
> GH1-NODE-01 --host <broker>`. The WiFi firmware mirrors it exactly on the wire.

---

## OTA (over-the-air) updates

- **WiFi node** — already on the network, so OTA stays available. Set
  `OTA_ENABLED 1` in `secrets.h`; `setup()` brings up `ArduinoOTA`. Flash over the
  air with the `esp32-wifi_ota` env:

  ```bash
  pio run -e esp32-wifi_ota -t upload --upload-port <node-ip>
  ```

- **LoRa node** — OTA is **stubbed/disabled by default** (no IP backhaul). If the
  board is separately WiFi-equipped, set `OTA_ENABLED 1`, fill `WIFI_SSID` /
  `WIFI_PASSWORD`, and flash with the `esp32dev_ota` env. The `OTA-READY` hooks in
  `src/main.cpp` open a brief update window before deep sleep.

In production, set an OTA password (or signed updates).

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
