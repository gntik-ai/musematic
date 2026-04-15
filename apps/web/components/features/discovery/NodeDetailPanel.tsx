"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DiscoveryHypothesis } from "@/lib/hooks/use-discovery-network";

interface NodeDetailPanelProps {
  hypothesis: DiscoveryHypothesis | null;
}

export function NodeDetailPanel({ hypothesis }: NodeDetailPanelProps) {
  if (!hypothesis) {
    return (
      <Card className="border-dashed bg-background/70">
        <CardHeader>
          <CardTitle className="text-base">Select a hypothesis</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Click a node to inspect Elo, confidence, cluster assignment, critiques, and experiments.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-background/90 shadow-sm">
      <CardHeader className="space-y-3">
        <Badge className="w-fit" variant="secondary">
          {hypothesis.cluster_id ?? "unclustered"}
        </Badge>
        <CardTitle className="text-lg leading-snug">{hypothesis.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-muted-foreground">{hypothesis.description}</p>
        <div className="grid grid-cols-2 gap-3">
          <Metric label="Elo" value={hypothesis.elo_score?.toFixed(1) ?? "n/a"} />
          <Metric label="Rank" value={hypothesis.rank ? `#${hypothesis.rank}` : "n/a"} />
          <Metric label="Confidence" value={`${Math.round(hypothesis.confidence * 100)}%`} />
          <Metric
            label="Record"
            value={`${hypothesis.wins}-${hypothesis.losses}-${hypothesis.draws}`}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-muted/40 p-3">
      <p className="text-[11px] uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
      <p className="mt-1 font-semibold text-foreground">{value}</p>
    </div>
  );
}
