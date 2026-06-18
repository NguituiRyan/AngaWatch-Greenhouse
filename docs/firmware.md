# Firmware (summary)

> This is a pointer/summary. The full, authoritative firmware documentation —
> wiring tables, build/flash commands, OTA, and per-probe calibration — lives in
> **[`../firmware/README.md`](../firmware/README.md)**.

The **Sense** layer of AngaWatch is a battery + solar **ESP32 + LoRa sensor node**,
authored in PlatformIO under `firmware/`. It is written for clarity and is **not
compiled in CI**; pin maps and calibration constants are sane placeholders to
verify against your exact hardware before flashing.

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
persists it.

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
├── platformio.ini        # env esp32dev, libs, deep-sleep build flags
├── include/
│   ├── config.h          # pins, LoRa params, identity, deep-sleep interval
│   └── thresholds.h      # instant microclimate thresholds (mirror backend)
└── src/
    ├── main.cpp          # read → threshold → JSON → TX → sleep
    ├── sensors.h/.cpp    # sensor drivers
    └── lora.h/.cpp       # SX1276/RFM95 init + send
```

Build / flash / monitor (from `firmware/`):

```bash
pio run -e esp32dev
pio run -e esp32dev -t upload
pio device monitor -b 115200
```

**OTA** is stubbed and disabled by default (standard nodes are LoRa-only with no IP
backhaul); a WiFi-equipped node can enable `OTA_ENABLED` and use the
`esp32dev_ota` env. Per-probe **calibration** (soil moisture, leaf wetness, PPFD,
battery divider, NPK register map) is documented in detail in the firmware README —
measure each probe, do not trust the placeholders.
