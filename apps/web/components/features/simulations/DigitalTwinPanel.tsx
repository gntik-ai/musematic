"use client";

import { Badge } from "@/components/ui/badge";
import { useDigitalTwin } from "@/lib/hooks/use-digital-twin";

export function DigitalTwinPanel({
  runId,
  reportId,
}: {
  runId: string;
  reportId?: string | null;
}) {
  const reportQuery = useDigitalTwin(runId, reportId);
  const report = reportQuery.data;

  return (
    <section className="space-y-4 rounded-lg border border-border/70 bg-card/80 p-4">
      <div>
        <h2 className="text-lg font-semibold">Digital twin divergence</h2>
        <p className="text-sm text-muted-foreground">
          Mock and real subsystem coverage, reference availability, and divergence points.
        </p>
      </div>
      {!report ? (
        <p className="text-sm text-muted-foreground">Digital twin report is loading.</p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <ListBlock title="Mock components" values={report.mock_components} />
          <ListBlock title="Real components" values={report.real_components} />
          <div className="space-y-3 rounded-lg border border-border/70 p-3">
            <h3 className="font-medium">Simulated vs wall clock</h3>
            <p className="text-sm text-muted-foreground">
              Simulated {formatDuration(report.simulated_time_ms)} / wall {formatDuration(report.wall_clock_time_ms)}
            </p>
            {report.reference_available ? (
              <Badge variant="outline">Reference {report.reference_execution_id}</Badge>
            ) : (
              <p className="text-sm text-muted-foreground">No reference available.</p>
            )}
          </div>
        </div>
      )}
      {report?.divergence_points.length ? (
        <div className="space-y-2">
          <h3 className="font-medium">Divergence points</h3>
          <div className="grid gap-2">
            {report.divergence_points.map((point, index) => (
              <pre
                className="overflow-x-auto rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs"
                key={`divergence-${index}`}
              >
                {JSON.stringify(point, null, 2)}
              </pre>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function ListBlock({ title, values }: { title: string; values: string[] }) {
  return (
    <div className="space-y-3 rounded-lg border border-border/70 p-3">
      <h3 className="font-medium">{title}</h3>
      {values.length ? (
        <div className="flex flex-wrap gap-2">
          {values.map((value) => (
            <Badge key={value} variant="secondary">
              {value}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No components listed.</p>
      )}
    </div>
  );
}

function formatDuration(value: number | null) {
  if (value === null) {
    return "n/a";
  }
  if (value < 1000) {
    return `${value} ms`;
  }
  return `${(value / 1000).toFixed(1)} s`;
}
