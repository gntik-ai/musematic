"use client";

import { useDiscoveryEvidence } from "@/lib/hooks/use-discovery-evidence";

export function EvidenceInspectorView({
  hypothesisId,
  workspaceId,
}: {
  hypothesisId: string;
  workspaceId: string;
}) {
  const evidenceQuery = useDiscoveryEvidence(hypothesisId, workspaceId);
  const items = [
    ...(evidenceQuery.data?.aggregated ? [evidenceQuery.data.aggregated] : []),
    ...(evidenceQuery.data?.items ?? []),
  ];

  if (!evidenceQuery.isLoading && items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
        Source unavailable or no critique evidence has been recorded for this hypothesis.
      </div>
    );
  }

  return (
    <section className="space-y-4">
      {items.map((item) => (
        <article className="rounded-lg border border-border bg-card p-4" key={item.critique_id}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold">
              {item.is_aggregated ? "Aggregated evidence" : item.reviewer_agent_fqn}
            </h2>
            <a
              className="text-sm text-brand-primary underline-offset-4 hover:underline"
              href={`/discovery/${encodeURIComponent(item.hypothesis_id)}/hypotheses`}
            >
              Source hypothesis
            </a>
          </div>
          <pre className="mt-3 overflow-x-auto rounded-md bg-muted p-3 text-xs">
            {JSON.stringify(item.scores, null, 2)}
          </pre>
        </article>
      ))}
    </section>
  );
}
