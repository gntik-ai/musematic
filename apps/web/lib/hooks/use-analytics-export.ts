"use client";

import { useState } from "react";
import { toast } from "@/lib/hooks/use-toast";
import type { AnalyticsFilters, UsageResponse } from "@/types/analytics";

function escapeCsv(value: string | number | null): string {
  if (value === null) {
    return "";
  }

  const text = String(value);
  if (!/[",\n]/.test(text)) {
    return text;
  }

  return `"${text.replaceAll('"', '""')}"`;
}

function buildCsvRows(data: UsageResponse): string[] {
  const header = [
    "date",
    "agent",
    "model",
    "provider",
    "cost",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "execution_count",
    "quality_score",
  ].join(",");

  const rows = data.items.map((item) =>
    [
      escapeCsv(item.period),
      escapeCsv(item.agent_fqn),
      escapeCsv(item.model_id),
      escapeCsv(item.provider),
      escapeCsv(item.cost_usd.toFixed(4)),
      escapeCsv(item.input_tokens),
      escapeCsv(item.output_tokens),
      escapeCsv(item.total_tokens),
      escapeCsv(item.execution_count),
      "",
    ].join(","),
  );

  return [header, ...rows];
}

function downloadCsv(csv: string, filename: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function useAnalyticsExport(): {
  exportToCsv: (data: UsageResponse, filters: AnalyticsFilters) => void;
  isExporting: boolean;
} {
  const [isExporting, setIsExporting] = useState(false);

  const exportToCsv = (data: UsageResponse, filters: AnalyticsFilters) => {
    setIsExporting(true);

    try {
      const csv = buildCsvRows(data).join("\n");
      const filename = `analytics-${filters.workspaceId}-${filters.from.slice(0, 10)}-${filters.to.slice(0, 10)}.csv`;

      if (data.items.length === 0) {
        toast({
          title: "No data",
          description: "No data matched the active filters.",
        });
      }

      downloadCsv(csv, filename);
    } finally {
      setIsExporting(false);
    }
  };

  return { exportToCsv, isExporting };
}
