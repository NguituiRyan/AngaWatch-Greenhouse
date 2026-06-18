# AngaWatch Web Dashboard

Multi-tenant operator dashboard for the AngaWatch Greenhouse platform.

- **Stack:** React 18 + TypeScript + Vite + Tailwind CSS + TanStack Query +
  Recharts + react-router-dom.
- **Auth:** OAuth2 password login against `/api/v1/auth/login`; the JWT is stored
  in `localStorage` and attached to every request by `src/lib/api.ts`.
- **Theming:** white-label aware — a reseller org's `theme.primary` colour
  overrides the `--brand` CSS variable at runtime (`src/context/ThemeProvider.tsx`).

## Configuration

```
VITE_API_BASE_URL=http://localhost:8000   # backend origin; `/api/v1` is appended
```

Copy `.env.example` to `.env` to override. The dev server runs on port 5173,
which the backend CORS config already allows.

## Develop

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check + production bundle to dist/
npm run preview    # serve the production build
npm run test       # vitest component/unit tests
```

## Structure

```
src/
  lib/        api fetch wrapper, shared types, formatting helpers
  context/    AuthContext (JWT) + ThemeProvider (white-label)
  hooks/      TanStack Query hooks per domain (auth/farms/.../weather)
  components/ layout shell, charts, reusable UI
  pages/      Dashboard, GreenhouseDetail, Alerts, Recommendations,
              Devices, Billing, Login, and scaffolded roadmap pages
```

## Implemented pages

- **Dashboard** — org overview: greenhouses with current risk badges, recent
  alerts feed (with ack), and device health.
- **Greenhouse detail** — live latest values, historical temp/RH/soil charts,
  current risk per model + recommendation, manual actuator control, device health.
- **Alerts** — filterable feed with inline acknowledge.
- **Recommendations** — EN/SW actions with an agronomist override form.
- **Devices** — org-wide health table (battery, last-seen, RSSI, status).
- **Billing** — subscription status, payment history, and an M-Pesa subscribe
  form that fires an STK push.

## Roadmap (scaffolded "coming soon")

Records, Invoicing, Input Marketplace, Market Linkage, Traceability/Export,
Financing, and Yield Forecasting render preview placeholders tagged with their
delivery Wave.
