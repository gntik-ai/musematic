import { format, parseISO } from "date-fns";
import { toTitleCase } from "@/lib/utils";

const usdFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const compactNumberFormatter = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
});

const analyticsPalette = [
  "hsl(var(--brand-primary))",
  "hsl(var(--brand-accent))",
  "hsl(var(--warning))",
  "hsl(var(--primary))",
  "hsl(var(--secondary-foreground))",
  "hsl(var(--muted-foreground))",
] as const;

export function formatAnalyticsPeriod(period: string): string {
  try {
    return format(parseISO(period), "MMM d");
  } catch {
    return period;
  }
}

export function formatUsd(value: number): string {
  return usdFormatter.format(value);
}

export function formatCompactNumber(value: number): string {
  return compactNumberFormatter.format(value);
}

export function analyticsColorAt(index: number): string {
  return analyticsPalette[index % analyticsPalette.length] ?? analyticsPalette[0];
}

export function humanizeAnalyticsKey(value: string): string {
  if (!value) {
    return "Unknown";
  }

  return toTitleCase(value.replaceAll(":", " "));
}

export function median(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }

  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    const lower = sorted[middle - 1];
    const upper = sorted[middle];
    if (lower === undefined || upper === undefined) {
      return 0;
    }
    return (lower + upper) / 2;
  }
  return sorted[middle] ?? 0;
}
