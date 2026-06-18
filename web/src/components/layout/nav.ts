/**
 * Sidebar navigation config.
 *
 * `implemented` items route to live pages; `roadmap` items are scaffolded
 * placeholders that show the Wave roadmap ("coming soon").
 */

export interface NavItem {
  to: string;
  label: string;
  /** Inline SVG path (heroicons-style 24px outline). */
  icon: string;
  wave?: string;
}

export interface NavSection {
  heading: string;
  items: NavItem[];
}

const ICONS = {
  home: "M3 9.75 12 3l9 6.75V20a1 1 0 0 1-1 1h-5v-6H10v6H4a1 1 0 0 1-1-1V9.75Z",
  greenhouse: "M4 21V10l8-6 8 6v11M9 21v-6h6v6",
  alerts: "M12 4a6 6 0 0 0-6 6v3l-2 3h16l-2-3v-3a6 6 0 0 0-6-6Zm0 17a2 2 0 0 0 2-2h-4a2 2 0 0 0 2 2Z",
  bulb: "M9 18h6M10 21h4M12 3a6 6 0 0 0-4 10.5c.6.7 1 1.6 1 2.5h6c0-.9.4-1.8 1-2.5A6 6 0 0 0 12 3Z",
  chip: "M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3M7 7h10v10H7z",
  card: "M3 7h18v10H3zM3 11h18",
  records: "M5 4h14v16H5zM8 8h8M8 12h8M8 16h5",
  invoice: "M6 3h12v18l-3-2-3 2-3-2-3 2V3Zm3 5h6M9 12h6",
  cart: "M3 4h2l2 12h11l2-8H7M9 20a1 1 0 1 0 0 .01M18 20a1 1 0 1 0 0 .01",
  market: "M4 9h16l-1-4H5L4 9Zm0 0v10h16V9M9 19v-5h6v5",
  trace: "M4 6h16M4 12h16M4 18h10M16 16l3 3 3-3",
  finance: "M12 3v18M7 7h6a3 3 0 0 1 0 6H8a3 3 0 0 0 0 6h7",
  chart: "M4 20V8M10 20V4M16 20v-7M22 20H2",
} as const;

export const NAV: NavSection[] = [
  {
    heading: "Operations",
    items: [
      { to: "/", label: "Dashboard", icon: ICONS.home },
      { to: "/alerts", label: "Alerts", icon: ICONS.alerts },
      { to: "/recommendations", label: "Recommendations", icon: ICONS.bulb },
      { to: "/devices", label: "Devices", icon: ICONS.chip },
      { to: "/billing", label: "Billing", icon: ICONS.card },
    ],
  },
  {
    heading: "Roadmap",
    items: [
      { to: "/records", label: "Records", icon: ICONS.records, wave: "Wave 1" },
      { to: "/invoicing", label: "Invoicing", icon: ICONS.invoice, wave: "Wave 1" },
      { to: "/marketplace", label: "Input Marketplace", icon: ICONS.cart, wave: "Wave 2" },
      { to: "/market", label: "Market Linkage", icon: ICONS.market, wave: "Wave 2" },
      { to: "/traceability", label: "Traceability / Export", icon: ICONS.trace, wave: "Wave 2" },
      { to: "/financing", label: "Financing", icon: ICONS.finance, wave: "Wave 3" },
      { to: "/forecasting", label: "Yield Forecasting", icon: ICONS.chart, wave: "Wave 3" },
    ],
  },
];
