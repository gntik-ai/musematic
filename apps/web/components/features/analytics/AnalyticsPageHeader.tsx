"use client";

import { format } from "date-fns";
import { CalendarDays, Download } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  DATE_RANGE_PRESET_LABELS,
  type AnalyticsDateRange,
  type DateRangePreset,
} from "@/types/analytics";

export interface AnalyticsPageHeaderProps {
  dateRange: AnalyticsDateRange;
  onDateRangeChange: (range: AnalyticsDateRange) => void;
  onExport: () => void;
  isExporting: boolean;
}

function formatInputDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function formatDateRangeLabel(range: AnalyticsDateRange): string {
  return `${format(range.from, "MMM d, yyyy")} - ${format(range.to, "MMM d, yyyy")}`;
}

export function AnalyticsPageHeader({
  dateRange,
  onDateRangeChange,
  onExport,
  isExporting,
}: AnalyticsPageHeaderProps) {
  const [draftFrom, setDraftFrom] = useState(formatInputDate(dateRange.from));
  const [draftTo, setDraftTo] = useState(formatInputDate(dateRange.to));
  const [calendarOpen, setCalendarOpen] = useState(false);

  const dateRangeLabel = useMemo(() => formatDateRangeLabel(dateRange), [dateRange]);

  const applyCustomRange = () => {
    const from = new Date(`${draftFrom}T00:00:00.000Z`);
    const to = new Date(`${draftTo}T23:59:59.999Z`);

    if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || from > to) {
      return;
    }

    onDateRangeChange({ from, to, preset: "custom" });
    setCalendarOpen(false);
  };

  const selectPreset = (preset: DateRangePreset) => {
    if (preset === "custom") {
      setCalendarOpen(true);
      return;
    }

    const now = new Date();
    const end = new Date(now);
    const start = new Date(now);
    const days = preset === "7d" ? 6 : preset === "30d" ? 29 : 89;
    start.setDate(now.getDate() - days);
    onDateRangeChange({ from: start, to: end, preset });
    setDraftFrom(formatInputDate(start));
    setDraftTo(formatInputDate(end));
  };

  return (
    <header className="overflow-hidden rounded-[2rem] border bg-[radial-gradient(circle_at_top_left,hsl(var(--brand-primary)/0.16),transparent_28%),linear-gradient(135deg,hsl(var(--card))_0%,hsl(var(--muted)/0.55)_100%)] p-6 shadow-sm">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-3">
          <div className="inline-flex w-fit items-center gap-2 rounded-full border border-border/60 bg-background/75 px-3 py-1 text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
            Cost intelligence
          </div>
          <div className="space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
              Analytics
            </h1>
            <p className="max-w-3xl text-sm text-muted-foreground md:text-base">
              Cost, token consumption, forecast pressure and drift signals for the
              active workspace.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3 lg:items-end">
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Date range presets">
            {(["7d", "30d", "90d", "custom"] as const).map((preset) => (
              <Button
                key={preset}
                aria-pressed={dateRange.preset === preset}
                size="sm"
                variant={dateRange.preset === preset ? "default" : "outline"}
                onClick={() => selectPreset(preset)}
              >
                {DATE_RANGE_PRESET_LABELS[preset]}
              </Button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
              <PopoverTrigger asChild>
                <Button className="justify-start" variant="outline">
                  <CalendarDays className="h-4 w-4" />
                  {dateRangeLabel}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[22rem] space-y-4">
                <div className="space-y-1">
                  <h2 className="font-medium">Custom range</h2>
                  <p className="text-sm text-muted-foreground">
                    Pick the exact window you want reflected across every chart.
                  </p>
                </div>
                <label className="grid gap-1 text-sm">
                  <span className="text-muted-foreground">From</span>
                  <input
                    className="h-10 rounded-md border border-border bg-background px-3"
                    type="date"
                    value={draftFrom}
                    onChange={(event) => setDraftFrom(event.target.value)}
                  />
                </label>
                <label className="grid gap-1 text-sm">
                  <span className="text-muted-foreground">To</span>
                  <input
                    className="h-10 rounded-md border border-border bg-background px-3"
                    type="date"
                    value={draftTo}
                    onChange={(event) => setDraftTo(event.target.value)}
                  />
                </label>
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" onClick={() => setCalendarOpen(false)}>
                    Cancel
                  </Button>
                  <Button onClick={applyCustomRange}>Apply range</Button>
                </div>
              </PopoverContent>
            </Popover>

            <Button
              aria-label="Export analytics data as CSV"
              disabled={isExporting}
              onClick={onExport}
            >
              <Download className="h-4 w-4" />
              {isExporting ? "Exporting…" : "Export CSV"}
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}
