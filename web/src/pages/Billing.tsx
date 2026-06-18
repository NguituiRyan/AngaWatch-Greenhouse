/**
 * Billing.
 *
 * Shows the org's current subscription, a payment history, and an M-Pesa
 * subscribe form that fires an STK push (POST /billing/subscribe). The customer
 * confirms the prompt on their phone; reconciliation lands via the Daraja
 * callback, so we surface the STK status optimistically here.
 */

import { useState, type FormEvent } from "react";

import { useSubscription, usePayments, useSubscribe } from "@/hooks/useBilling";
import type { PlanType } from "@/lib/types";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/Badge";
import { EmptyState, ErrorState, Spinner } from "@/components/ui/States";
import { formatDateTime, humanize } from "@/lib/format";

const PLANS: PlanType[] = ["subscription", "rent_to_own", "daas"];

function subTone(status: string): string {
  if (status === "active") return "green";
  if (status === "trial") return "blue";
  if (status === "past_due" || status === "suspended") return "amber";
  return "slate";
}

function payTone(status: string): string {
  if (status === "success") return "green";
  if (status === "failed" || status === "reversed") return "red";
  return "amber";
}

function SubscribeForm() {
  const subscribe = useSubscribe();
  const [phone, setPhone] = useState("+254700000001");
  const [amount, setAmount] = useState(500);
  const [planType, setPlanType] = useState<PlanType>("subscription");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    await subscribe.mutateAsync({
      plan_type: planType,
      phone: phone.trim(),
      amount,
      plan_name: "standard",
    });
  }

  const result = subscribe.data;

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div>
        <label className="label" htmlFor="plan">
          Plan
        </label>
        <select
          id="plan"
          className="input"
          value={planType}
          onChange={(e) => setPlanType(e.target.value as PlanType)}
        >
          {PLANS.map((p) => (
            <option key={p} value={p}>
              {humanize(p)}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="phone">
            M-Pesa phone
          </label>
          <input
            id="phone"
            className="input"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+2547…"
            required
          />
        </div>
        <div>
          <label className="label" htmlFor="amount">
            Amount (KES)
          </label>
          <input
            id="amount"
            type="number"
            min={1}
            className="input"
            value={amount}
            onChange={(e) => setAmount(Number(e.target.value))}
            required
          />
        </div>
      </div>

      <button type="submit" className="btn-primary w-full" disabled={subscribe.isPending}>
        {subscribe.isPending ? "Sending STK push…" : "Subscribe via M-Pesa"}
      </button>

      {subscribe.isError ? (
        <p className="rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          {(subscribe.error as Error).message}
        </p>
      ) : null}

      {result ? (
        <div
          className={`rounded-lg px-3 py-2 text-sm ${
            result.ok ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800"
          }`}
        >
          {result.ok
            ? (result.customer_message ?? "STK push sent. Confirm on your phone.")
            : (result.error ?? "STK push could not be initiated.")}
        </div>
      ) : null}
    </form>
  );
}

export function BillingPage() {
  const subscription = useSubscription();
  const payments = usePayments();

  return (
    <div>
      <PageHeader title="Billing" subtitle="Subscription and M-Pesa payments" />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <Card title="Current subscription">
            {subscription.isLoading ? (
              <Spinner />
            ) : subscription.error ? (
              <ErrorState error={subscription.error} />
            ) : !subscription.data ? (
              <EmptyState title="No active subscription" hint="Subscribe to unlock premium features." />
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-lg font-semibold text-slate-900">
                      {humanize(subscription.data.plan_name)}
                    </p>
                    <p className="text-xs text-slate-400">
                      {humanize(subscription.data.plan_type)} ·{" "}
                      {subscription.data.currency} {subscription.data.price.toFixed(0)}/
                      {subscription.data.billing_interval}
                    </p>
                  </div>
                  <StatusPill
                    label={humanize(subscription.data.status)}
                    tone={subTone(subscription.data.status)}
                  />
                </div>
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-slate-400">Trial ends</dt>
                    <dd className="text-slate-700">{formatDateTime(subscription.data.trial_ends_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-400">Period ends</dt>
                    <dd className="text-slate-700">
                      {formatDateTime(subscription.data.current_period_end)}
                    </dd>
                  </div>
                </dl>
              </div>
            )}
          </Card>

          <Card title="Payment history">
            {payments.isLoading ? (
              <Spinner />
            ) : payments.error ? (
              <ErrorState error={payments.error} />
            ) : (payments.data ?? []).length === 0 ? (
              <EmptyState title="No payments yet" />
            ) : (
              <div className="divide-y divide-slate-100">
                {payments.data!.map((p) => (
                  <div key={p.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                    <div className="min-w-0">
                      <p className="font-medium text-slate-800">
                        {p.currency} {p.amount.toFixed(0)}
                      </p>
                      <p className="truncate text-xs text-slate-400">
                        {humanize(p.provider)} · {formatDateTime(p.initiated_at)}
                        {p.mpesa_receipt ? ` · ${p.mpesa_receipt}` : ""}
                      </p>
                    </div>
                    <StatusPill label={humanize(p.status)} tone={payTone(p.status)} />
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <Card title="Subscribe">
          <SubscribeForm />
        </Card>
      </div>
    </div>
  );
}
