/**
 * Roadmap placeholder page.
 *
 * Each scaffolded feature (records, invoicing, marketplace, market linkage,
 * traceability, financing, yield forecasting) renders this with its planned
 * Wave and a short description of what is coming.
 */

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { StatusPill } from "@/components/ui/Badge";

interface ComingSoonProps {
  title: string;
  wave: string;
  description: string;
  bullets: string[];
}

export function ComingSoon({ title, wave, description, bullets }: ComingSoonProps) {
  return (
    <div>
      <PageHeader
        title={title}
        subtitle={description}
        actions={<StatusPill label={`${wave} · Coming soon`} tone="blue" />}
      />

      <Card>
        <div className="flex flex-col items-center gap-4 py-8 text-center">
          <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand/10 text-brand">
            <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth={1.6}>
              <path d="M12 8v4l3 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Z" strokeLinecap="round" />
            </svg>
          </span>
          <div>
            <p className="text-base font-semibold text-slate-800">Planned for {wave}</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
              This module is on the AngaWatch roadmap. The screen below previews what it will offer.
            </p>
          </div>
          <ul className="mx-auto grid max-w-lg gap-2 text-left">
            {bullets.map((b) => (
              <li key={b} className="flex items-start gap-2 text-sm text-slate-600">
                <svg
                  viewBox="0 0 24 24"
                  className="mt-0.5 h-4 w-4 shrink-0 text-brand"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path d="m5 12 5 5 9-11" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {b}
              </li>
            ))}
          </ul>
        </div>
      </Card>
    </div>
  );
}
