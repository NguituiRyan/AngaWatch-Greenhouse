/**
 * Self-contained DEMO MODE.
 *
 * When `VITE_DEMO_MODE === "true"` (set for production builds via
 * `.env.production`) the api layer serves baked-in fixtures — captured verbatim
 * from a live backend running the late-blight scenario — instead of making
 * network calls. This lets the dashboard run on Vercel with **no backend**.
 *
 * A few mutations (alert ack, actuator command, subscribe, recommendation
 * override) update in-memory copies so the UI stays interactive within a session.
 * `npm run dev` (development mode) does NOT set the flag, so local dev still talks
 * to the real FastAPI backend.
 */

import demoData from "./demo-data.json";

export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const d = demoData as any;

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}

// Mutable session state, seeded from the immutable fixtures.
const state = {
  alerts: clone<Record<string, unknown>[]>(d.alerts ?? []),
  recommendations: clone<Record<string, unknown>[]>(d.recommendations ?? []),
  actuators: clone<Record<string, unknown>[]>(d.actuators ?? []),
  commands: clone<Record<string, unknown>[]>(d.commands ?? []),
  subscription: clone<Record<string, unknown> | null>(d.subscription ?? null),
};

function nowIso(): string {
  return new Date().toISOString();
}

function handlePost(path: string, body: Record<string, unknown> | undefined): unknown {
  if (path === "/auth/login") {
    return {
      access_token: "demo-access-token",
      refresh_token: "demo-refresh-token",
      token_type: "bearer",
    };
  }

  let m: RegExpMatchArray | null;

  if ((m = path.match(/^\/alerts\/([^/]+)\/ack$/))) {
    const alert = state.alerts.find((a) => a.id === m![1]);
    if (alert) {
      alert.status = "acked";
      alert.acked_at = nowIso();
    }
    return alert ?? {};
  }

  if ((m = path.match(/^\/recommendations\/([^/]+)\/override$/))) {
    const rec = state.recommendations.find((r) => r.id === m![1]);
    if (rec) {
      rec.overridden = true;
      rec.override_message = body?.message ?? "";
      rec.override_at = nowIso();
    }
    return rec ?? {};
  }

  if ((m = path.match(/^\/actuators\/([^/]+)\/command$/))) {
    const command = String(body?.command ?? "open");
    const actuator = state.actuators[0];
    if (actuator) {
      actuator.state = command === "open" ? "open" : command === "close" ? "closed" : command;
      actuator.last_state_change = nowIso();
    }
    const record = {
      id: `demo-cmd-${state.commands.length + 1}`,
      actuator_device_id: m[1],
      command,
      params: body?.params ?? {},
      status: "acked",
      source: "manual",
      issued_at: nowIso(),
      acked_at: nowIso(),
      error: null,
    };
    state.commands.unshift(record);
    return record;
  }

  if (path === "/billing/subscribe") {
    if (state.subscription) {
      state.subscription.status = "active";
    }
    return {
      ok: true,
      checkout_request_id: "demo-checkout-request",
      merchant_request_id: "demo-merchant-request",
      customer_message: "Demo mode: M-Pesa STK push simulated — subscription is now active.",
      error: null,
    };
  }

  return {};
}

function handleGet(path: string): unknown {
  if (path === "/auth/me") return d.me;
  if (path === "/organizations/me") return d.org;

  if (path === "/farms") return d.farms;
  if (/^\/farms\/[^/]+\/weather$/.test(path)) return d.weather;
  if (/^\/farms\/[^/]+$/.test(path)) return d.farms?.[0] ?? null;

  if (/\/readings\/latest$/.test(path)) return d.readingsLatest;
  if (/\/readings$/.test(path)) return d.readings;
  if (/\/risk\/history$/.test(path)) return d.riskHistory;
  if (/\/risk$/.test(path)) return d.risk;
  if (/\/actuators$/.test(path)) return state.actuators;

  if (path === "/greenhouses") return d.greenhouses;
  if (/^\/greenhouses\/[^/]+$/.test(path)) return d.greenhouse;

  if (path === "/control/commands") return state.commands;
  if (path === "/alerts") return state.alerts;
  if (path === "/recommendations") return state.recommendations;
  if (path === "/devices") return d.devices;

  if (path === "/billing/subscription") return state.subscription;
  if (path === "/billing/payments") return d.payments;

  return null;
}

/** Resolve a request against the fixtures, with a touch of latency for realism. */
export async function demoRequest<T>(
  method: string,
  path: string,
  body: unknown,
): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, 120));
  const result =
    method === "GET"
      ? handleGet(path)
      : method === "POST"
        ? handlePost(path, body as Record<string, unknown> | undefined)
        : {};
  return result as T;
}
