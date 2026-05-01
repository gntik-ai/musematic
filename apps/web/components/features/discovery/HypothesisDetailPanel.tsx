"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useDiscoveryEvidence } from "@/lib/hooks/use-discovery-evidence";
import type { DiscoveryHypothesis } from "@/types/discovery";

export function HypothesisDetailPanel({
  hypothesis,
  workspaceId,
}: {
  hypothesis: DiscoveryHypothesis;
  workspaceId: string;
}) {
  const evidenceQuery = useDiscoveryEvidence(hypothesis.hypothesis_id, workspaceId);
  const evidenceCount =
    (evidenceQuery.data?.items.length ?? 0) + (evidenceQuery.data?.aggregated ? 1 : 0);

  return (
    <aside className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div>
        <h2 className="text-lg font-semibold">{hypothesis.title}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{hypothesis.reasoning}</p>
      </div>
      <div className="space-y-2 text-sm">
        <p>Evidence pointers: {evidenceCount}</p>
        <p>Related cluster: {hypothesis.cluster_id ?? "Unclustered"}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button asChild>
          <Link
            href={`/discovery/${encodeURIComponent(hypothesis.session_id)}/experiments/new?hypothesis=${encodeURIComponent(hypothesis.hypothesis_id)}`}
          >
            Launch Experiment
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link
            href={`/discovery/${encodeURIComponent(hypothesis.session_id)}/evidence/${encodeURIComponent(hypothesis.hypothesis_id)}`}
          >
            Inspect Evidence
          </Link>
        </Button>
      </div>
    </aside>
  );
}
