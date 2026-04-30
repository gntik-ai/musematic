"use client";

import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { EmptyState } from "@/components/shared/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceSummary } from "@/lib/hooks/use-workspace-summary";
import { ActiveGoalsCard } from "./_components/ActiveGoalsCard";
import { AgentCountCard } from "./_components/AgentCountCard";
import { BudgetGaugeCard } from "./_components/BudgetGaugeCard";
import { DLPViolationsCountCard } from "./_components/DLPViolationsCountCard";
import { ExecutionsInFlightCard } from "./_components/ExecutionsInFlightCard";
import { QuotaUsageBarsCard } from "./_components/QuotaUsageBarsCard";
import { RecentActivityFeed } from "./_components/RecentActivityFeed";
import { TagSummaryCard } from "./_components/TagSummaryCard";

export default function WorkspaceDashboardPage() {
  const params = useParams<{ id: string }>();
  const summary = useWorkspaceSummary(params.id);
  const t = useTranslations("workspaces.dashboard");

  return (
    <WorkspaceOwnerLayout
      title={t("title")}
      description={t("description")}
    >
      {summary.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="h-36 rounded-lg" />
          ))}
        </div>
      ) : null}

      {summary.isError ? (
        <EmptyState title={t("unavailable")} description={t("unavailableDescription")} />
      ) : null}

      {summary.data ? (
        <div className="space-y-5">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <ActiveGoalsCard value={summary.data.active_goals} />
            <ExecutionsInFlightCard value={summary.data.executions_in_flight} />
            <AgentCountCard value={summary.data.agent_count} />
            <DLPViolationsCountCard value={summary.data.dlp_violations} />
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <BudgetGaugeCard budget={summary.data.budget} />
            <QuotaUsageBarsCard quotas={summary.data.quotas} />
            <TagSummaryCard tags={summary.data.tags} />
          </div>
          <RecentActivityFeed items={summary.data.recent_activity} />
        </div>
      ) : null}
    </WorkspaceOwnerLayout>
  );
}
