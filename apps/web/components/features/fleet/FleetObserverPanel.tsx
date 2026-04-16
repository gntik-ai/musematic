"use client";

import { format } from "date-fns";
import { Info, OctagonAlert, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useAcknowledgeFinding, useObserverFindings } from "@/lib/hooks/use-observer-findings";
import type { ObserverFindingSeverity } from "@/lib/types/fleet";

interface FleetObserverPanelProps {
  fleetId: string;
}

function severityMeta(severity: ObserverFindingSeverity) {
  if (severity === "critical") {
    return {
      className:
        "border-rose-300 bg-rose-50 text-rose-900 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-100",
      icon: OctagonAlert,
    };
  }
  if (severity === "warning") {
    return {
      className:
        "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100",
      icon: TriangleAlert,
    };
  }
  return {
    className:
      "border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-800 dark:bg-sky-950 dark:text-sky-100",
    icon: Info,
  };
}

export function FleetObserverPanel({ fleetId }: FleetObserverPanelProps) {
  const [severity, setSeverity] = useState<ObserverFindingSeverity | null>(null);
  const [showAcknowledged, setShowAcknowledged] = useState(false);
  const findingsQuery = useObserverFindings(fleetId, {
    severity,
    acknowledged: showAcknowledged ? null : false,
    limit: 100,
  });
  const acknowledgeFindingMutation = useAcknowledgeFinding();

  const acknowledged = useMemo(
    () => (findingsQuery.data?.items ?? []).filter((item) => item.acknowledged),
    [findingsQuery.data?.items],
  );
  const openFindings = useMemo(
    () => (findingsQuery.data?.items ?? []).filter((item) => !item.acknowledged),
    [findingsQuery.data?.items],
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-4 rounded-3xl border border-border/60 bg-card/80 p-5 shadow-sm lg:flex-row lg:items-end lg:justify-between">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-2 text-sm">
            <span className="font-medium">Severity</span>
            <Select
              aria-label="Finding severity"
              value={severity ?? ""}
              onChange={(event) =>
                setSeverity(
                  event.target.value
                    ? (event.target.value as ObserverFindingSeverity)
                    : null,
                )
              }
            >
              <option value="">All</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </Select>
          </label>
          <div className="space-y-2 text-sm">
            <span className="font-medium">Show acknowledged</span>
            <div className="flex items-center gap-3">
              <Switch checked={showAcknowledged} onCheckedChange={setShowAcknowledged} />
              <span className="text-muted-foreground">
                Include acknowledged findings
              </span>
            </div>
          </div>
        </div>
      </div>

      <section className="space-y-3">
        <h3 className="text-lg font-semibold">Open findings</h3>
        {openFindings.map((finding) => {
          const meta = severityMeta(finding.severity);
          const Icon = meta.icon;
          return (
            <article
              key={finding.id}
              className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 shadow-sm"
            >
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-3">
                  <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${meta.className}`}>
                    <Icon className="h-3.5 w-3.5" />
                    {finding.severity}
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">
                      {format(new Date(finding.created_at), "PPp")} · {finding.observer_name}
                    </p>
                    <p className="mt-2 text-base">{finding.description}</p>
                  </div>
                  <details className="rounded-2xl border border-border/50 bg-background/60 p-4">
                    <summary className="cursor-pointer text-sm font-medium">
                      Suggested actions
                    </summary>
                    <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
                      {finding.suggested_actions.map((action) => (
                        <li key={action}>{action}</li>
                      ))}
                    </ul>
                  </details>
                </div>
                <Button
                  aria-label={`Acknowledge finding ${finding.id}`}
                  disabled={acknowledgeFindingMutation.isPending}
                  onClick={() => {
                    void acknowledgeFindingMutation.mutateAsync({
                      fleetId,
                      findingId: finding.id,
                    });
                  }}
                >
                  Acknowledge
                </Button>
              </div>
            </article>
          );
        })}
        {openFindings.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-border/70 px-4 py-6 text-sm text-muted-foreground">
            No open findings for the active filter.
          </p>
        ) : null}
      </section>

      {showAcknowledged ? (
        <section className="space-y-3">
          <h3 className="text-lg font-semibold">Acknowledged</h3>
          {acknowledged.map((finding) => (
            <article
              key={finding.id}
              className="rounded-[1.75rem] border border-border/60 bg-card/80 p-5 shadow-sm"
            >
              <p className="text-sm text-muted-foreground">
                {finding.observer_name} · acknowledged {finding.acknowledged_at ? format(new Date(finding.acknowledged_at), "PPp") : "just now"}
              </p>
              <p className="mt-2">{finding.description}</p>
            </article>
          ))}
        </section>
      ) : null}
    </div>
  );
}

