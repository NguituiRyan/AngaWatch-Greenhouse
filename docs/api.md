# REST API

The backend exposes a JSON REST API under the **`/api/v1`** prefix. The live,
authoritative schema (request/response shapes, validation, examples) is the
**OpenAPI** document served by the running app:

- Swagger UI: **`http://localhost:8000/docs`**
- ReDoc: **`http://localhost:8000/redoc`**
- Raw schema: `http://localhost:8000/openapi.json`

This page is a **summary only** — for field-level detail, defer to OpenAPI.

---

## Auth & conventions

- **Auth:** JWT bearer. Get a token from `POST /api/v1/auth/login` (OAuth2
  password form; `username` = the user's email). Send it as
  `Authorization: Bearer <access_token>`. Refresh via `POST /auth/refresh`.
- **Org scoping:** every authenticated endpoint is scoped to the caller's
  `org_id` (`OrgScope`). Cross-tenant resources return **404**.
- **Roles:** `farmer`, `agronomist`, `coop_admin`, `super_admin`. `super_admin`
  is always allowed where a role gate is present.
- **Feature gates:** premium endpoints require an active/trial subscription whose
  plan grants the feature, else **402 Payment Required**.
- **Webhooks** (`/billing/mpesa/callback`, `/ussd`, `/whatsapp/webhook`) are
  **unauthenticated** by design — they are called by external providers.

---

## Endpoint summary

| Method & path (under `/api/v1`) | Auth | Notes |
| ------------------------------- | ---- | ----- |
| `GET /health`, `GET /` (root) | none | Liveness + service banner. |
| **Auth** | | |
| `POST /auth/login` | none | OAuth2 password form → `{access_token, refresh_token, token_type}`. |
| `POST /auth/register` | none | Create a user. |
| `GET /auth/me` | bearer | Current user. |
| `POST /auth/refresh` | none | Refresh token → new access token. |
| **Organizations** | | |
| `GET /organizations/me` | bearer | The caller's org. |
| `PATCH /organizations/...` | super_admin | Org updates. |
| **Farms / Greenhouses / Devices** | | |
| `GET/POST /farms`, `GET/PATCH/DELETE /farms/{id}` | bearer | Org-scoped CRUD. |
| `GET/POST /greenhouses`, `GET/PATCH/DELETE /greenhouses/{id}` | bearer | Org-scoped CRUD. |
| `GET/POST /devices`, `GET/PATCH/DELETE /devices/{id}` | bearer | Org-scoped CRUD. |
| **Readings** | | |
| `GET /greenhouses/{id}/readings` | bearer | Timeseries (`metric`, `start`, `end`, `limit`). |
| `GET /greenhouses/{id}/readings/latest` | bearer | Most recent reading. |
| `POST /ingest` | bearer | Optional HTTP telemetry ingest. |
| **Risk** | | |
| `GET /greenhouses/{id}/risk` | bearer | Latest assessment per model. |
| `GET /greenhouses/{id}/risk/history` | bearer + `dashboard_history` | Assessment timeline (premium feature gate). |
| **Alerts / Recommendations** | | |
| `GET /alerts` | bearer | Filter by `status`. |
| `POST /alerts/{id}/ack` | bearer | Acknowledge. |
| `GET /recommendations` | bearer | List. |
| `POST /recommendations/{id}/override` | agronomist / coop_admin | Store an override (training signal). |
| **Control** | | |
| `GET /greenhouses/{id}/actuators` | bearer | Actuators in a greenhouse. |
| `POST /actuators/{id}/command` | bearer | Manually enqueue **and** execute (`{command, params?}`). |
| `GET /control/commands` | bearer | Command history. |
| **Billing** | | |
| `GET /billing/subscription` | bearer | Current subscription (nullable). |
| `POST /billing/subscribe` | bearer | `{plan_type, phone, amount}` → triggers M-Pesa STK. |
| `POST /billing/mpesa/callback` | **none** | Daraja webhook (reconciles by `checkout_request_id`). |
| `GET /billing/payments` | bearer | Payment history. |
| **Weather** | | |
| `GET /farms/{id}/weather` | bearer | Latest observation + upcoming forecasts. |
| **Messaging webhooks** | | |
| `POST /ussd` | **none** | Africa's Talking USSD (form-encoded → `text/plain` `CON`/`END` menu). |
| `GET /whatsapp/webhook` | **none** | Meta verify challenge. |
| `POST /whatsapp/webhook` | **none** | Inbound WhatsApp messages. |
| **Records** (Wave 1 scaffold) | | |
| `GET/POST /spray-logs` | bearer | List + create. |
| `GET/POST /harvest-logs` | bearer | List + create. |
| `GET/POST /expenses` | bearer | List + create. Per-cycle PHI/cost/yield rollups deferred (TODO → 501). |

---

## Not yet exposed

The ORM tables for **invoicing, the input marketplace, market linkage, solar
dryers, financing/credit-scoring, and traceability** exist (see
[`data-model.md`](data-model.md)) but have **no REST routers yet** — they are Wave
2–3. Status per area is tracked in [`../NOTES.md`](../NOTES.md).
