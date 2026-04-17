"use client";

import { use } from "react";
import { useMemo, useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { AgentRevisionTimeline } from "@/components/features/agent-management/AgentRevisionTimeline";
import { RevisionDiffViewer } from "@/components/features/agent-management/RevisionDiffViewer";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";

export default function AgentRevisionsPage({
  params,
}: {
  params: Promise<{ fqn: string }>;
}) {
  const router = useRouter();
  const resolvedParams = use(params);
  const fqn = useMemo(
    () => decodeURIComponent(resolvedParams.fqn),
    [resolvedParams.fqn],
  );
  const [selectedRevisions, setSelectedRevisions] = useState<[number, number] | null>(
    null,
  );

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand-accent">
            {fqn}
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Revision history</h1>
          <p className="mt-2 max-w-3xl text-muted-foreground">
            Compare historical versions and roll back safely when a previous revision should be restored.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => router.push(`/agent-management/${encodeURIComponent(fqn)}`)}
        >
          Back to agent
        </Button>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr,1.1fr]">
        <AgentRevisionTimeline
          fqn={fqn}
          onRollback={() => {
            setSelectedRevisions(null);
          }}
          onSelectForDiff={(revisions) => setSelectedRevisions(revisions)}
        />
        {selectedRevisions ? (
          <RevisionDiffViewer
            baseRevision={selectedRevisions[0]}
            compareRevision={selectedRevisions[1]}
            fqn={fqn}
          />
        ) : (
          <EmptyState
            description="Select exactly two revisions from the timeline to render the YAML diff."
            icon={ArrowLeftRight}
            title="No diff selected"
          />
        )}
      </div>
    </section>
  );
}
