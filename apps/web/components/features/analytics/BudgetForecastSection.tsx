"use client";

import { AlertTriangle } from "lucide-react";
import { useMemo } from "react";
import { SectionError } from "@/components/features/home/SectionError";
import { BudgetUtilizationBar } from "@/components/features/analytics/BudgetUtilizationBar";
import { ForecastChart } from "@/components/features/analytics/ForecastChart";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalyticsKpi } from "@/lib/hooks/use-analytics-kpi";
import { useCostForecast } from "@/lib/hooks/use-cost-forecast";
import { useAnalyticsStore } from "@/lib/stores/use-analytics-store";
import {
  FORECAST_HORIZON_LABELS,
  type AnalyticsFilters,
  type ForecastChartPoint,
} from "@/types/analytics";

interface BudgetForecastSectionProps {
  workspaceName: string;
  currentPeriodFilters: AnalyticsFilters;
}

const forecastHorizons = [7, 30, 90] as const;

export function BudgetForecastSection({
  workspaceName,
  currentPeriodFilters,
}: BudgetForecastSectionProps) {
  const forecastHorizon = useAnalyticsStore((state) => state.forecastHorizon);
  const setForecastHorizon = useAnalyticsStore((state) => state.setForecastHorizon);
  const kpiQuery = useAnalyticsKpi(currentPeriodFilters);
  const forecastQuery = useCostForecast(
    currentPeriodFilters.workspaceId,
    forecastHorizon,
  );

  const currentSpend = useMemo(
    () =>
      (kpiQuery.data?.items ?? []).reduce(
        (sum, item) => sum + item.total_cost_usd,
        0,
      ),
    [kpiQuery.data?.items],
  );

  const chartData = useMemo<ForecastChartPoint[]>(
    () =>
      (forecastQuery.data?.daily_forecast ?? []).map((point) => ({
        date: point.date,
        low: point.projected_cost_usd_low,
        expected: point.projected_cost_usd_expected,
        high: point.projected_cost_usd_high,
      })),
    [forecastQuery.data?.daily_forecast],
  );

  const handleHorizonKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
    currentHorizon: (typeof forecastHorizons)[number],
  ) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
      return;
    }

    event.preventDefault();
    const currentIndex = forecastHorizons.indexOf(currentHorizon);
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex =
      (currentIndex + direction + forecastHorizons.length) % forecastHorizons.length;
    setForecastHorizon(forecastHorizons[nextIndex] ?? 30);
  };

  return (
    <Card className="rounded-[1.75rem]">
      <CardHeader>
        <CardTitle>Budget forecast</CardTitle>
        <p className="text-sm text-muted-foreground">
          Track present spend and project where the active workspace is headed next.
        </p>
      </CardHeader>
      <CardContent className="space-y-5">
        <div
          aria-label="Forecast horizon selector"
          className="flex flex-wrap gap-2"
          role="group"
        >
          {forecastHorizons.map((horizon) => (
            <Button
              key={horizon}
              aria-pressed={forecastHorizon === horizon}
              size="sm"
              tabIndex={0}
              variant={forecastHorizon === horizon ? "default" : "outline"}
              onKeyDown={(event) => handleHorizonKeyDown(event, horizon)}
              onClick={() => setForecastHorizon(horizon)}
            >
              {FORECAST_HORIZON_LABELS[horizon]}
            </Button>
          ))}
        </div>

        {forecastQuery.data?.high_volatility ? (
          <Alert>
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-[hsl(var(--warning))]" />
              <div>
                <AlertTitle>High volatility detected</AlertTitle>
                <AlertDescription>
                  Forecast confidence is wide because recent cost patterns have been unstable.
                </AlertDescription>
              </div>
            </div>
          </Alert>
        ) : null}

        {(forecastQuery.data?.data_points_used ?? 999) < 7 ? (
          <Alert>
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-[hsl(var(--warning))]" />
              <div>
                <AlertTitle>Low data volume</AlertTitle>
                <AlertDescription>
                  Fewer than seven historical data points were available for the forecast.
                </AlertDescription>
              </div>
            </div>
          </Alert>
        ) : null}

        {kpiQuery.isPending ? (
          <Skeleton className="h-24 rounded-[1.25rem]" />
        ) : kpiQuery.isError ? (
          <SectionError
            message="Current-period spend could not be loaded."
            title="Budget utilization unavailable"
          />
        ) : (
          <BudgetUtilizationBar
            allocatedBudgetUsd={null}
            currentSpendUsd={currentSpend}
            workspaceName={workspaceName}
          />
        )}

        {forecastQuery.isPending ? (
          <Skeleton className="h-[300px] rounded-[1.25rem]" />
        ) : forecastQuery.isError ? (
          <SectionError
            message="Forecast data could not be loaded."
            title="Forecast unavailable"
          />
        ) : (
          <ForecastChart
            data={chartData}
            totalProjectedExpected={forecastQuery.data?.total_projected_expected ?? 0}
            trendDirection={forecastQuery.data?.trend_direction ?? "stable"}
          />
        )}
      </CardContent>
    </Card>
  );
}
