"use client";

import { useMemo, useState } from "react";
import {
  CheckCircle2,
  CircleOff,
  GitBranch,
  Loader2,
  XCircle,
} from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  ReasoningBranch,
  ReasoningBranchStatus,
  ReasoningTrace,
} from "@/types/reasoning";

const branchStatusConfig: Record<
  ReasoningBranchStatus,
  { icon: typeof Loader2; label: string; className: string }
> = {
  active: {
    icon: Loader2,
    label: "Active",
    className: "text-brand-primary",
  },
  completed: {
    icon: CheckCircle2,
    label: "Completed",
    className: "text-emerald-600 dark:text-emerald-300",
  },
  pruned: {
    icon: CircleOff,
    label: "Pruned",
    className: "text-muted-foreground",
  },
  failed: {
    icon: XCircle,
    label: "Failed",
    className: "text-destructive",
  },
};

function BranchCard({
  branch,
  branchesByParent,
}: {
  branch: ReasoningBranch;
  branchesByParent: Map<string | null, ReasoningBranch[]>;
}) {
  const children = branchesByParent.get(branch.id) ?? [];
  const status = branchStatusConfig[branch.status];
  const StatusIcon = status.icon;

  return (
    <Collapsible defaultOpen={branch.depth === 0}>
      <div className="rounded-2xl border border-border/70 bg-card/80 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <CollapsibleTrigger className="flex items-center gap-3 text-left">
            <StatusIcon
              className={`h-4 w-4 ${status.className} ${branch.status === "active" ? "animate-spin" : ""}`}
            />
            <div>
              <p className="font-medium text-foreground">{branch.id}</p>
              <p className="text-sm text-muted-foreground">{status.label}</p>
            </div>
          </CollapsibleTrigger>

          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">{branch.tokenUsage.totalTokens} tokens</Badge>
            <Badge variant="outline">Depth {branch.depth}</Badge>
            {branch.budgetRemainingAtCompletion !== null ? (
              <Badge variant="outline">
                {branch.budgetRemainingAtCompletion} budget left
              </Badge>
            ) : null}
          </div>
        </div>

        <CollapsibleContent>
          <div className="mt-4 space-y-4 border-t border-border/60 pt-4">
            <ol className="space-y-2">
              {branch.chainOfThought.map((thought) => (
                <li
                  className="rounded-xl border border-border/60 bg-background/80 p-3 text-sm"
                  key={`${branch.id}-${thought.index}`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-foreground">
                      Thought {thought.index}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {thought.tokenCost} tokens
                    </span>
                  </div>
                  <p className="mt-2 text-muted-foreground">{thought.thought}</p>
                  {thought.confidence !== null ? (
                    <p className="mt-2 text-xs text-muted-foreground">
                      Confidence {(thought.confidence * 100).toFixed(0)}%
                    </p>
                  ) : null}
                </li>
              ))}
            </ol>

            {children.length > 0 ? (
              <div className="space-y-3 border-l border-border pl-4">
                {children.map((child) => (
                  <BranchCard
                    branch={child}
                    branchesByParent={branchesByParent}
                    key={child.id}
                  />
                ))}
              </div>
            ) : null}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}

export function ReasoningTraceViewer({
  isLoading,
  reasoningTrace,
}: {
  isLoading?: boolean;
  reasoningTrace: ReasoningTrace | null | undefined;
}) {
  const [visibleCount, setVisibleCount] = useState(6);

  const visibleBranches = useMemo(
    () => reasoningTrace?.branches.slice(0, visibleCount) ?? [],
    [reasoningTrace?.branches, visibleCount],
  );
  const visibleIds = useMemo(
    () => new Set(visibleBranches.map((branch) => branch.id)),
    [visibleBranches],
  );
  const branchesByParent = useMemo(() => {
    const map = new Map<string | null, ReasoningBranch[]>();

    visibleBranches.forEach((branch) => {
      const key =
        branch.parentId && visibleIds.has(branch.parentId)
          ? branch.parentId
          : null;
      map.set(key, [...(map.get(key) ?? []), branch]);
    });

    return map;
  }, [visibleBranches, visibleIds]);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 rounded-xl" />
        <Skeleton className="h-28 rounded-xl" />
      </div>
    );
  }

  if (!reasoningTrace || reasoningTrace.branches.length === 0) {
    return (
      <EmptyState
        description="No reasoning traces were emitted for this step."
        icon={GitBranch}
        title="No reasoning traces available"
      />
    );
  }

  const rootBranches = branchesByParent.get(null) ?? [];

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-border/70 bg-card/80 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold text-foreground">Reasoning tree</h3>
            <p className="text-sm text-muted-foreground">
              {reasoningTrace.totalBranches} branches explored in{" "}
              {reasoningTrace.budgetSummary.mode}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">
              {reasoningTrace.budgetSummary.usedTokens}/
              {reasoningTrace.budgetSummary.maxTokens} tokens
            </Badge>
            <Badge variant="outline">
              {reasoningTrace.budgetSummary.usedRounds}/
              {reasoningTrace.budgetSummary.maxRounds} rounds
            </Badge>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {rootBranches.map((branch) => (
          <BranchCard
            branch={branch}
            branchesByParent={branchesByParent}
            key={branch.id}
          />
        ))}
      </div>

      {visibleCount < reasoningTrace.totalBranches ? (
        <Button
          onClick={() => {
            setVisibleCount((count) => count + 6);
          }}
          variant="outline"
        >
          Load more branches
        </Button>
      ) : null}
    </div>
  );
}
