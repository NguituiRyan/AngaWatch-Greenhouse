# AngaWatch Edge Gateway

A small, standalone **store-and-forward MQTT bridge** that runs on-farm (e.g. a
Raspberry Pi sitting next to the local Mosquitto broker). It makes telemetry
delivery **offline-first**: no reading is ever lost, even across power cuts and
the long connectivity gaps typical of rural Kenyan sites.

```
 sensor nodes ──▶ LOCAL broker ──▶ [ gateway ] ──▶ CLOUD broker ──▶ backend ingestion
   farm/#         (Mosquitto)        store &           (MQTT)
                                     forward
                                        │
                                        ▼
                                  SQLite buffer
                                  (durable, WAL)
```

## How it works

1. **Subscribe + buffer.** The gateway connects to the **local** broker and
   subscribes to `farm/#`. Every message received is written to a durable
   on-disk SQLite queue **before** any forward attempt — so a crash or power
   loss between receive and forward cannot drop data.
2. **Batch-forward when online.** A background flush loop pulls batches of
   unsent messages and republishes them (preserving the original topic and
   payload bytes) to the **cloud** broker. With QoS ≥ 1 a row is only marked
   `sent` after the cloud broker acknowledges the publish — at-least-once
   delivery.
3. **Offline-first with backoff.** If the cloud broker is unreachable, messages
   simply keep accumulating in SQLite and the loop retries with exponential
   backoff (`backoff_initial` → `backoff_max`). When connectivity returns the
   whole backlog drains in batches automatically.
4. **Self-housekeeping.** Already-forwarded rows older than
   `GATEWAY_PURGE_AFTER_DAYS` are purged hourly to reclaim disk. Unsent rows are
   **never** purged regardless of age.

The gateway depends only on `paho-mqtt` and the Python standard library
(`sqlite3`); it does **not** import the backend `app.*` package, so it deploys
on minimal edge hardware.

## Telemetry contract

The gateway is payload-agnostic: it forwards raw bytes on whatever topic they
arrived. Nodes publish to `farm/{org_id}/{device_uid}/telemetry` (see
`docs/CONTRACT.md`), and the gateway preserves that topic end to end so the
cloud-side `app.ingestion.consumer` sees exactly what the node sent.

## Run it

```bash
# from the gateway/ directory
pip install -e .
python -m gateway.run
```

By default everything points at `localhost:1883`, so against a single local
Mosquitto broker it just runs (local == cloud is fine for a smoke test).

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `GATEWAY_LOCAL_HOST` / `GATEWAY_LOCAL_PORT` | `localhost` / `1883` | On-farm broker the nodes publish to |
| `GATEWAY_LOCAL_USERNAME` / `GATEWAY_LOCAL_PASSWORD` | — | Local broker auth (optional) |
| `GATEWAY_CLOUD_HOST` / `GATEWAY_CLOUD_PORT` | `localhost` / `1883` | Upstream cloud broker |
| `GATEWAY_CLOUD_USERNAME` / `GATEWAY_CLOUD_PASSWORD` | — | Cloud broker auth (optional) |
| `GATEWAY_CLOUD_TLS` | `false` | Use TLS to the cloud broker |
| `GATEWAY_SUBSCRIBE_TOPIC` | `farm/#` | Local subscription filter |
| `GATEWAY_DB_PATH` | `gateway_buffer.sqlite` | Durable buffer file |
| `GATEWAY_BATCH_SIZE` | `100` | Max messages forwarded per flush |
| `GATEWAY_FLUSH_INTERVAL` | `5.0` | Seconds between flush attempts |
| `GATEWAY_BACKOFF_INITIAL` / `GATEWAY_BACKOFF_MAX` | `2.0` / `300.0` | Retry backoff bounds on cloud failure |
| `GATEWAY_PURGE_AFTER_DAYS` | `7` | Retention for already-sent rows |
| `GATEWAY_QOS` | `1` | MQTT QoS for subscribe + forward |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Components

- `config.py` — env-driven `GatewayConfig` / `BrokerConfig` (frozen dataclasses).
- `store.py` — `SqliteBuffer`: `enqueue` / `pending` / `mark_sent` / `purge`,
  WAL-mode, thread-safe, crash-durable.
- `forwarder.py` — `Forwarder`: the dual-broker bridge and flush/backoff loop.
- `run.py` — `python -m gateway.run` entrypoint with signal handling.

## Tests

```bash
# using the backend venv (paho-mqtt already installed there)
cd ..   # repo root
backend/.venv/Scripts/python.exe -m pytest gateway/tests -q
```

The test suite covers the durable buffer's `enqueue` / `pending` / `mark_sent`
roundtrip, the `limit`, idempotency, retry-counter, purge-retention, and
restart-durability behaviours.
