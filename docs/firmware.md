# Firmware (summary)

> This is a pointer/summary. The full, authoritative firmware documentation —
> wiring tables, build/flash commands, OTA, and per-probe calibration — lives in
> **[`../firmware/README.md`](../firmware/README.md)**.

The **Sense** layer of AngaWatch is an **ESP32 sensor node** authored in PlatformIO
under `firmware/`, with **two backhauls** you pick per deployment:

- **`esp32dev`** — battery + solar **LoRa** node (SX1276/RFM95, 868 MHz) that deep-sleeps
  and forwards to a field gateway. Long range, ultra-low power, telemetry-only.
- **`esp32-wifi`** — a mains/solar-buffered **WiFi + MQTT** node (`src/main_wifi.cpp`,
  PubSubClient) that talks **directly to the broker**, stays awake, and **closes the
  control loop**: it subscribes to commands and drives the vent relay, publishing a
  state ack the dashboard confirms. See **[`hardware-integration.md`](hardware-integration.md)**.

It is written for clarity and is **not compiled in CI**; pin maps and calibration
constants are sane placeholders to verify against your exact hardware before flashing.

---

## What the node does

A node runs an RTC deep-sleep duty cycle (~15 min):

1. **Wake** on the RTC timer.
2. **Read** the sensor bus: SHT4x air temp + RH, DS18B20 soil temp, capacitive
   soil moisture, leaf-wetness grid, PPFD, RS485 (Modbus) NPK probe, pheromone-trap
   beam-break, and battery voltage.
3. **Run instant threshold rules locally** (`include/thresholds.h`) and trip a
   local relay/buzzer if a band is exceeded — so a farmer still gets an alert when
   the network is down.
4. **Encode** a telemetry JSON packet matching `app.schemas.telemetry.TelemetryIn`.
5. **Transmit** over 868 MHz LoRa (SX1276/RFM95) to the field gateway.
6. **Sleep**.

The gateway validates and republishes each packet to MQTT
`farm/{org_id}/{device_uid}/telemetry`, where the backend ingestion consumer
persists it. The **`esp32-wifi`** node skips the gateway — it publishes straight to
that topic, and additionally subscribes to `.../command` and publishes `.../state`
to close the actuator control loop with the dashboard.

---

## On-device threshold rules

`firmware/include/thresholds.h` is the node's offline safety net and **mirrors the
backend `microclimate` risk model**. Keep these in sync with the
`RiskModelConfig` defaults if re-tuned in the field — they are field-calibratable.

| Constant | Value | Action |
| -------- | ----- | ------ |
| `AIR_TEMP_VENT` | 35 °C | vent now (HIGH) |
| `RH_FUNGAL_WARN` | 85 % | fungal-pressure warning (MEDIUM) |
| `SOIL_IRRIGATE_MIN` | 25 % | irrigate (MEDIUM) |
| `SOIL_IRRIGATE_CRIT` | 15 % | irrigate, critical (HIGH) |

The cloud risk engine remains the source of truth for the **windowed** and
**forecast-fused** models (late blight, *Tuta absoluta*, nutrient, water); the node
only re-implements the **instant** rules for offline alerting. See
[`risk-models.md`](risk-models.md).

---

## Layout & build (pointers)

```
firmware/
├── platformio.ini        # envs: esp32dev (LoRa) + esp32-wifi (WiFi/MQTT)
├── include/
│   ├── config.h          # pins (incl. PIN_VENT_RELAY), LoRa/MQTT params, identity
│   ├── secrets.h.example  # copy -> secrets.h: WiFi + MQTT + ORG_ID + uids (gitignored)
│   └── thresholds.h      # instant microclimate thresholds (mirror backend)
└── src/
    ├── main.cpp          # LoRa node: read → threshold → JSON → TX → sleep
    ├── main_wifi.cpp     # WiFi node: telemetry up + command down + relay + state ack
    ├── sensors.h/.cpp    # sensor drivers
    └── lora.h/.cpp       # SX1276/RFM95 init + send
```

Build / flash / monitor (from `firmware/`):

```bash
pio run -e esp32dev        -t upload   # LoRa node
pio run -e esp32-wifi      -t upload   # WiFi+MQTT node (closes the dashboard loop)
pio device monitor -b 115200
```

> The WiFi node needs `include/secrets.h` (copy from `secrets.h.example`) with your
> WiFi + broker + the **Organization UUID** (not the slug) and matching `DEVICE_UID`.
> Build with `-DSIMULATE_SENSORS` to run with no sensors wired.

**OTA** is available on the WiFi node (`esp32-wifi_ota`); LoRa-only nodes have no IP
backhaul. Per-probe **calibration** (soil moisture, leaf wetness, PPFD, battery
divider, NPK register map) is documented in the firmware README — measure each
probe, do not trust the placeholders.
