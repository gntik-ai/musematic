"use client";

import { format } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { humanizeMarketplaceValue, type AgentRevision } from "@/lib/types/marketplace";

export interface AgentRevisionsProps {
  revisions: AgentRevision[];
  currentVersion: string;
}

export function AgentRevisions({
  revisions,
  currentVersion,
}: AgentRevisionsProps) {
  return (
    <ol className="space-y-3">
      {revisions.map((revision) => {
        const isCurrent = revision.version === currentVersion || revision.isCurrent;

        return (
          <li
            key={revision.version}
            className="rounded-2xl border border-border/60 bg-card/70 p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="font-medium">{revision.version}</p>
                <p className="text-sm text-muted-foreground">
                  {format(new Date(revision.publishedAt), "MMM d, yyyy")}
                </p>
              </div>
              {isCurrent ? (
                <Badge className="bg-emerald-500/15 text-emerald-700 dark:text-emerald-300" variant="outline">
                  Current
                </Badge>
              ) : null}
            </div>
            <p className="mt-3 text-sm text-muted-foreground">
              {revision.changeDescription || humanizeMarketplaceValue("no-release-notes")}
            </p>
          </li>
        );
      })}
    </ol>
  );
}
