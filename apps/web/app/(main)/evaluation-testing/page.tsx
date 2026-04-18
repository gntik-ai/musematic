"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { FlaskConical } from "lucide-react";
import { EvalSuiteDataTable } from "@/components/features/eval/EvalSuiteDataTable";
import { EmptyState } from "@/components/shared/EmptyState";
import { useEvalSets } from "@/lib/hooks/use-eval-sets";
import {
  DEFAULT_EVAL_LIST_FILTERS,
  type EvalListFilters,
} from "@/types/evaluation";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function EvaluationTestingPage() {
  const router = useRouter();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const [filters, setFilters] = useState<EvalListFilters>(DEFAULT_EVAL_LIST_FILTERS);
  const evalSetsQuery = useEvalSets(workspaceId ?? "", filters);

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before browsing evaluation suites."
        icon={FlaskConical}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Eval suites</h1>
        <p className="text-sm text-muted-foreground md:text-base">
          Browse benchmark suites, inspect run quality, and drill into verdict-level scoring.
        </p>
      </header>
      <EvalSuiteDataTable
        data={evalSetsQuery.data?.items ?? []}
        filters={filters}
        isLoading={evalSetsQuery.isLoading}
        onCreate={() => router.push("/evaluation-testing/new")}
        onFiltersChange={(nextValues) =>
          setFilters((current) => ({ ...current, ...nextValues }))
        }
        onRowClick={(evalSetId) => router.push(`/evaluation-testing/${encodeURIComponent(evalSetId)}`)}
        totalCount={evalSetsQuery.data?.total ?? 0}
      />
    </section>
  );
}
