/**
 * App routes.
 *
 * Public: /login. Everything else is behind <ProtectedRoute> inside the app
 * shell (sidebar + topbar). Implemented pages route to live views; roadmap
 * pages render "coming soon" previews.
 */

import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "@/components/layout/ProtectedRoute";
import { AppLayout } from "@/components/layout/AppLayout";
import { LoginPage } from "@/pages/Login";
import { DashboardPage } from "@/pages/Dashboard";
import { GreenhouseDetailPage } from "@/pages/GreenhouseDetail";
import { AlertsPage } from "@/pages/Alerts";
import { RecommendationsPage } from "@/pages/Recommendations";
import { DevicesPage } from "@/pages/Devices";
import { BillingPage } from "@/pages/Billing";
import { NotFoundPage } from "@/pages/NotFound";
import {
  RecordsPage,
  InvoicingPage,
  MarketplacePage,
  MarketLinkagePage,
  TraceabilityPage,
  FinancingPage,
  ForecastingPage,
} from "@/pages/RoadmapPages";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="greenhouses/:greenhouseId" element={<GreenhouseDetailPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="recommendations" element={<RecommendationsPage />} />
          <Route path="devices" element={<DevicesPage />} />
          <Route path="billing" element={<BillingPage />} />

          {/* Roadmap (scaffolded) */}
          <Route path="records" element={<RecordsPage />} />
          <Route path="invoicing" element={<InvoicingPage />} />
          <Route path="marketplace" element={<MarketplacePage />} />
          <Route path="market" element={<MarketLinkagePage />} />
          <Route path="traceability" element={<TraceabilityPage />} />
          <Route path="financing" element={<FinancingPage />} />
          <Route path="forecasting" element={<ForecastingPage />} />

          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
