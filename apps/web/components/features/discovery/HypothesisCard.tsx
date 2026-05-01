"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import type { DiscoveryHypothesis } from "@/types/discovery";

export function HypothesisCard({
  hypothesis,
  href,
}: {
  hypothesis: DiscoveryHypothesis;
  href: string;
}) {
  return (
    <Link
      className="block rounded-lg border border-border bg-card p-4 transition-colors hover:bg-accent/60"
      href={href}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{hypothesis.status}</Badge>
        <Badge className={confidenceClass(hypothesis.confidence)} variant="secondary">
          {confidenceTier(hypothesis.confidence)}
        </Badge>
        <Badge variant="outline">{Math.round(hypothesis.confidence * 100)}%</Badge>
        {hypothesis.rank ? <Badge variant="outline">Rank {hypothesis.rank}</Badge> : null}
      </div>
      <h2 className="mt-3 text-lg font-semibold">{hypothesis.title}</h2>
      <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">
        {hypothesis.description}
      </p>
      <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>Novelty {hypothesis.elo_score?.toFixed(0) ?? "n/a"}</span>
        <span>Evidence {hypothesis.wins + hypothesis.draws}</span>
        <span>{hypothesis.generating_agent_fqn}</span>
      </div>
    </Link>
  );
}

export function confidenceTier(value: number) {
  if (value >= 0.75) {
    return "high confidence";
  }
  if (value >= 0.45) {
    return "medium confidence";
  }
  return "low confidence";
}

function confidenceClass(value: number) {
  if (value >= 0.75) {
    return "bg-emerald-500/15 text-emerald-700";
  }
  if (value >= 0.45) {
    return "bg-amber-500/15 text-amber-700";
  }
  return "bg-destructive/10 text-foreground";
}
