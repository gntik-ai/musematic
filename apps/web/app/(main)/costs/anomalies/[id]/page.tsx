"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { AnomalyCard } from "@/components/features/cost-governance/AnomalyCard";
import { ForecastChart } from "@/components/features/cost-governance/ForecastChart";
import { EmptyState } from "@/components/shared/EmptyState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { acknowledgeAnomaly, resolveAnomaly, useAnomaly } from "@/lib/api/costs";

export default function CostAnomalyDetailPage() {
  const params = useParams<{ id: string }>();
  const anomaly = useAnomaly(params.id);
  const [notes, setNotes] = useState("");

  if (!anomaly.data) {
    return <EmptyState title="Anomaly unavailable" description="The anomaly could not be loaded." />;
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Anomaly Detail</h1>
      </div>
      <AnomalyCard
        anomaly={anomaly.data}
        onAcknowledge={(id) => {
          void acknowledgeAnomaly(id, notes);
        }}
        onResolve={(id) => {
          void resolveAnomaly(id);
        }}
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Baseline vs Observed</CardTitle>
          </CardHeader>
          <CardContent>
            <ForecastChart
              forecast={{
                id: anomaly.data.id,
                workspace_id: anomaly.data.workspace_id,
                period_start: anomaly.data.period_start,
                period_end: anomaly.data.period_end,
                forecast_cents: anomaly.data.observed_cents,
                confidence_interval: {
                  status: "ok",
                  low_cents: anomaly.data.baseline_cents,
                  high_cents: anomaly.data.observed_cents,
                },
                currency: "USD",
                computed_at: anomaly.data.detected_at,
              }}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Audit Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
