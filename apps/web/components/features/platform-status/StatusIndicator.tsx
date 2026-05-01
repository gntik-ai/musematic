"use client";

import {
  AlertTriangle,
  CheckCircle2,
  CircleAlert,
  Info,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { OverallState } from "@/lib/hooks/use-platform-status";

type IndicatorSeverity = "info" | "warning" | "critical" | "success";

interface StatusIndicatorProps {
  state?: OverallState | undefined;
  severity?: IndicatorSeverity | undefined;
  label: string;
  className?: string | undefined;
}

const severityByState: Record<OverallState, IndicatorSeverity> = {
  operational: "success",
  degraded: "info",
  partial_outage: "warning",
  full_outage: "critical",
  maintenance: "warning",
};

const classes: Record<IndicatorSeverity, string> = {
  success: "text-emerald-700",
  info: "text-sky-700",
  warning: "text-amber-700",
  critical: "text-red-700",
};

function Icon({ severity }: { severity: IndicatorSeverity }) {
  if (severity === "success") {
    return <CheckCircle2 aria-hidden className="h-4 w-4" />;
  }
  if (severity === "critical") {
    return <CircleAlert aria-hidden className="h-4 w-4" />;
  }
  if (severity === "warning") {
    return <AlertTriangle aria-hidden className="h-4 w-4" />;
  }
  return <Info aria-hidden className="h-4 w-4" />;
}

export function StatusIndicator({
  className,
  label,
  severity,
  state,
}: StatusIndicatorProps) {
  const resolvedSeverity = severity ?? (state ? severityByState[state] : "info");

  return (
    <span className={cn("inline-flex items-center gap-2", classes[resolvedSeverity], className)}>
      {state === "maintenance" ? <Wrench aria-hidden className="h-4 w-4" /> : <Icon severity={resolvedSeverity} />}
      <span className="font-medium">{label}</span>
    </span>
  );
}
