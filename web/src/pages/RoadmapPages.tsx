/** Scaffolded roadmap pages — each previews a future Wave module. */

import { ComingSoon } from "./ComingSoon";

export function RecordsPage() {
  return (
    <ComingSoon
      title="Records"
      wave="Wave 1"
      description="Spray, harvest and expense logs for every crop cycle."
      bullets={[
        "Spray logs with active ingredient, dose and pre-harvest interval (PHI)",
        "Harvest logs by quantity and grade",
        "Expense tracking toward cost-of-production",
        "PHI-compliance and cost rollups per crop cycle",
      ]}
    />
  );
}

export function InvoicingPage() {
  return (
    <ComingSoon
      title="Invoicing"
      wave="Wave 1"
      description="Generate and track buyer invoices from harvest records."
      bullets={[
        "Draft, issue and mark invoices paid",
        "Link invoices to harvest logs and buyers",
        "Overdue tracking and reminders",
      ]}
    />
  );
}

export function MarketplacePage() {
  return (
    <ComingSoon
      title="Input Marketplace"
      wave="Wave 2"
      description="Order seeds, fertigation inputs and crop-protection products."
      bullets={[
        "Browse a catalogue of vetted input products",
        "Place and track input orders",
        "Bundle recommendations driven by current risk",
      ]}
    />
  );
}

export function MarketLinkagePage() {
  return (
    <ComingSoon
      title="Market Linkage"
      wave="Wave 2"
      description="Connect growers to buyers and open market listings."
      bullets={[
        "Publish produce listings to a buyer network",
        "Match offers and confirm sales",
        "Aggregate cooperative supply for better prices",
      ]}
    />
  );
}

export function TraceabilityPage() {
  return (
    <ComingSoon
      title="Traceability / Export"
      wave="Wave 2"
      description="Farm-to-export traceability records for compliance."
      bullets={[
        "Per-batch traceability from spray to harvest",
        "Export-grade compliance documentation",
        "QR-linked provenance for buyers",
      ]}
    />
  );
}

export function FinancingPage() {
  return (
    <ComingSoon
      title="Financing"
      wave="Wave 3"
      description="Credit scoring and financing from your farm data."
      bullets={[
        "Credit profile built from yield and payment history",
        "Rent-to-own and input-financing options",
        "Installment schedules tied to M-Pesa",
      ]}
    />
  );
}

export function ForecastingPage() {
  return (
    <ComingSoon
      title="Yield Forecasting"
      wave="Wave 3"
      description="Predict yields from telemetry and crop-cycle history."
      bullets={[
        "Season yield projections per greenhouse",
        "Scenario planning against weather forecasts",
        "Early warnings for under-performing cycles",
      ]}
    />
  );
}
