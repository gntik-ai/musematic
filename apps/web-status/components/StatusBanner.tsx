import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  Wrench,
  XCircle,
} from "lucide-react";

import type { OverallState } from "@/lib/status-client";

type StatusBannerProps = {
  state: OverallState;
  label: string;
  detail?: string;
  stale?: boolean;
};

const variants: Record<
  OverallState,
  {
    icon: typeof CheckCircle2;
    className: string;
    labelClassName: string;
  }
> = {
  operational: {
    icon: CheckCircle2,
    className: "border-emerald-300 bg-emerald-50 text-emerald-950",
    labelClassName: "text-emerald-700",
  },
  degraded: {
    icon: Activity,
    className: "border-amber-300 bg-amber-50 text-amber-950",
    labelClassName: "text-amber-700",
  },
  partial_outage: {
    icon: CircleAlert,
    className: "border-orange-300 bg-orange-50 text-orange-950",
    labelClassName: "text-orange-700",
  },
  full_outage: {
    icon: XCircle,
    className: "border-red-300 bg-red-50 text-red-950",
    labelClassName: "text-red-700",
  },
  maintenance: {
    icon: Wrench,
    className: "border-sky-300 bg-sky-50 text-sky-950",
    labelClassName: "text-sky-700",
  },
};

export function StatusBanner({
  state,
  label,
  detail,
  stale = false,
}: StatusBannerProps) {
  const variant = variants[state] ?? variants.degraded;
  const Icon = stale ? AlertTriangle : variant.icon;
  return (
    <section
      aria-label="Platform status"
      aria-live="polite"
      className={`flex items-start gap-3 rounded-md border p-4 shadow-sm ${variant.className}`}
      data-state={state}
    >
      <Icon aria-hidden="true" className="mt-0.5 h-6 w-6 shrink-0" />
      <div className="min-w-0">
        <p className={`text-sm font-semibold uppercase tracking-normal ${variant.labelClassName}`}>
          {stale ? "Status data is stale" : label}
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-normal text-balance md:text-3xl">
          {state === "operational" && !stale ? "All systems operational" : label}
        </h1>
        {detail ? <p className="mt-2 max-w-3xl text-sm leading-6">{detail}</p> : null}
      </div>
    </section>
  );
}
