"use client";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { DiscoveryCluster } from "@/lib/hooks/use-discovery-network";

interface ClusterLegendProps {
  clusters: DiscoveryCluster[];
  selectedCluster: string | null;
  onSelectCluster: (cluster: string | null) => void;
}

const palette = [
  "bg-cyan-400",
  "bg-emerald-400",
  "bg-amber-400",
  "bg-rose-400",
  "bg-sky-500",
  "bg-lime-400",
];

export function clusterColor(clusterLabel: string | null): string {
  if (!clusterLabel) {
    return "bg-slate-400";
  }
  const hash = Array.from(clusterLabel).reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return palette[hash % palette.length] ?? "bg-slate-400";
}

export function ClusterLegend({
  clusters,
  selectedCluster,
  onSelectCluster,
}: ClusterLegendProps) {
  return (
    <div className="rounded-3xl border bg-background/85 p-4 shadow-sm backdrop-blur">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold">Clusters</p>
          <p className="text-xs text-muted-foreground">Filter the landscape by theme.</p>
        </div>
        <Button
          size="sm"
          variant={selectedCluster ? "outline" : "secondary"}
          onClick={() => onSelectCluster(null)}
        >
          All
        </Button>
      </div>
      <div className="flex flex-wrap gap-2">
        {clusters.map((cluster) => (
          <button
            className={cn(
              "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition",
              selectedCluster === cluster.cluster_label
                ? "border-foreground bg-foreground text-background"
                : "bg-muted/50 hover:bg-muted",
            )}
            key={cluster.cluster_label}
            onClick={() => onSelectCluster(cluster.cluster_label)}
            type="button"
          >
            <span className={cn("h-2.5 w-2.5 rounded-full", clusterColor(cluster.cluster_label))} />
            {cluster.cluster_label}
            <span className="text-muted-foreground">{cluster.hypothesis_count}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
