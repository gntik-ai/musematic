"use client";

import { endOfDay, formatISO, parseISO, startOfDay, subDays } from "date-fns";
import { useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AnalyticsPageHeader } from "@/components/features/analytics/AnalyticsPageHeader";
import { BudgetForecastSection } from "@/components/features/analytics/BudgetForecastSection";
import { CostEfficiencySection } from "@/components/features/analytics/CostEfficiencySection";
import { CostOverviewSection } from "@/components/features/analytics/CostOverviewSection";
import { DriftDashboardSection } from "@/components/features/analytics/DriftDashboardSection";
import { TokenConsumptionSection } from "@/components/features/analytics/TokenConsumptionSection";
import { EmptyState } from "@/components/shared/EmptyState";
import { useAnalyticsExport } from "@/lib/hooks/use-analytics-export";
import { useAnalyticsUsage } from "@/lib/hooks/use-analytics-usage";
import type {
  AnalyticsDateRange,
  AnalyticsFilters,
  DateRangePreset,
  Granularity,
} from "@/types/analytics";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

function isPreset(value: string | null): value is DateRangePreset {
  return value === "7d" || value === "30d" || value === "90d" || value === "custom";
}

function inferGranularity(from: Date, to: Date): Granularity {
  const days = Math.ceil((to.getTime() - from.getTime()) / (24 * 60 * 60 * 1000));
  return days > 90 ? "monthly" : "daily";
}

function defaultDateRange(): AnalyticsDateRange {
  const to = endOfDay(new Date());
  const from = startOfDay(subDays(to, 29));
  return { from, to, preset: "30d" };
}

function parseDateRange(
  searchParams: ReturnType<typeof useSearchParams>,
): AnalyticsDateRange {
  const fromValue = searchParams.get("from");
  const toValue = searchParams.get("to");
  const presetValue = searchParams.get("preset");
  const fallback = defaultDateRange();

  if (!fromValue || !toValue) {
    return fallback;
  }

  const from = startOfDay(parseISO(fromValue));
  const to = endOfDay(parseISO(toValue));
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || from > to) {
    return fallback;
  }

  return {
    from,
    to,
    preset: isPreset(presetValue) ? presetValue : "custom",
  };
}

function buildFilters(
  workspaceId: string | null | undefined,
  dateRange: AnalyticsDateRange,
): AnalyticsFilters | null {
  if (!workspaceId) {
    return null;
  }

  return {
    workspaceId,
    from: formatISO(dateRange.from),
    to: formatISO(dateRange.to),
    granularity: inferGranularity(dateRange.from, dateRange.to),
  };
}

export default function AnalyticsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentWorkspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const workspaceName =
    useWorkspaceStore((state) => state.currentWorkspace?.name ?? null) ??
    "Current workspace";
  const dateRange = useMemo(() => parseDateRange(searchParams), [searchParams]);
  const filters = useMemo(() => buildFilters(workspaceId, dateRange), [workspaceId, dateRange]);
  const exportQuery = useAnalyticsExport();
  const usageQuery = useAnalyticsUsage(filters);

  const updateDateRange = (nextRange: AnalyticsDateRange) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set("from", nextRange.from.toISOString().slice(0, 10));
    params.set("to", nextRange.to.toISOString().slice(0, 10));
    params.set("preset", nextRange.preset);
    router.push(`/analytics?${params.toString()}`);
  };

  if (!filters) {
    return (
      <section className="space-y-6">
        <AnalyticsPageHeader
          dateRange={dateRange}
          isExporting={false}
          onDateRangeChange={updateDateRange}
          onExport={() => {}}
        />
        <EmptyState
          description="Select a workspace to see cost intelligence and usage analytics."
          title="Analytics unavailable"
        />
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <AnalyticsPageHeader
        dateRange={dateRange}
        isExporting={exportQuery.isExporting}
        onDateRangeChange={updateDateRange}
        onExport={() => {
          exportQuery.exportToCsv(
            usageQuery.data ?? {
              items: [],
              total: 0,
              workspace_id: filters.workspaceId,
              granularity: filters.granularity,
              start_time: filters.from,
              end_time: filters.to,
            },
            filters,
          );
        }}
      />

      <CostOverviewSection filters={filters} />
      <TokenConsumptionSection filters={filters} />
      <CostEfficiencySection filters={filters} />
      <BudgetForecastSection
        currentPeriodFilters={filters}
        workspaceName={workspaceName}
      />
      <DriftDashboardSection filters={filters} />
    </section>
  );
}
