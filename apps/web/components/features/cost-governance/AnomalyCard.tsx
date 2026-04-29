"use client";

import Link from "next/link";
import { CheckCircle2, CircleAlert, ExternalLink, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { CostAnomalyResponse } from "@/lib/api/costs";

interface AnomalyCardProps {
  anomaly: CostAnomalyResponse;
  onAcknowledge?: (id: string) => void;
  onResolve?: (id: string) => void;
}

const severityVariant: Record<string, "default" | "destructive" | "secondary" | "outline"> = {
  low: "secondary",
  medium: "outline",
  high: "default",
  critical: "destructive",
};

export function AnomalyCard({ anomaly, onAcknowledge, onResolve }: AnomalyCardProps) {
  return (
    <article className="rounded-lg border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <CircleAlert className="h-4 w-4 text-amber-500" />
            <Badge variant={severityVariant[anomaly.severity] ?? "secondary"}>{anomaly.severity}</Badge>
            <Badge variant="outline">{anomaly.state}</Badge>
          </div>
          <p className="text-sm font-medium">{anomaly.summary}</p>
          <p className="text-xs text-muted-foreground">
            ${(Number(anomaly.baseline_cents) / 100).toFixed(2)} baseline · $
            {(Number(anomaly.observed_cents) / 100).toFixed(2)} observed
          </p>
        </div>
        <Button asChild size="icon" variant="ghost">
          <Link aria-label={`Open anomaly ${anomaly.id}`} href={`/costs/anomalies/${anomaly.id}`}>
            <ExternalLink className="h-4 w-4" />
          </Link>
        </Button>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {anomaly.state === "open" ? (
          <Button size="sm" variant="outline" onClick={() => onAcknowledge?.(anomaly.id)}>
            <CheckCircle2 className="mr-2 h-4 w-4" />
            Acknowledge
          </Button>
        ) : null}
        {anomaly.state !== "resolved" ? (
          <Button size="sm" variant="outline" onClick={() => onResolve?.(anomaly.id)}>
            <XCircle className="mr-2 h-4 w-4" />
            Resolve
          </Button>
        ) : null}
      </div>
    </article>
  );
}
