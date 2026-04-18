import { describe, expect, it } from "vitest";
import {
  analyticsColorAt,
  formatAnalyticsPeriod,
  formatCompactNumber,
  formatUsd,
  humanizeAnalyticsKey,
  median,
} from "@/lib/analytics";

describe("analytics helpers", () => {
  it("formats analytics periods and falls back for invalid dates", () => {
    expect(formatAnalyticsPeriod("2026-04-18T10:30:00.000Z")).toBe("Apr 18");
    expect(formatAnalyticsPeriod("not-a-date")).toBe("not-a-date");
  });

  it("formats currency and compact numbers", () => {
    expect(formatUsd(1234.56)).toBe("$1,234.56");
    expect(formatCompactNumber(12500)).toBe("12.5K");
  });

  it("cycles palette colors and humanizes analytics keys", () => {
    expect(analyticsColorAt(0)).toContain("--brand-primary");
    expect(analyticsColorAt(7)).toContain("hsl(");
    expect(analyticsColorAt(Number.NaN)).toContain("--brand-primary");
    expect(humanizeAnalyticsKey("provider:openai")).toBe("Provider Openai");
    expect(humanizeAnalyticsKey("")).toBe("Unknown");
  });

  it("computes median for empty, odd and even data sets", () => {
    expect(median([])).toBe(0);
    expect(median([5, 1, 9])).toBe(5);
    expect(median([2, 8, 4, 6])).toBe(5);
    expect(median(new Array<number>(2) as unknown as number[])).toBe(0);
  });
});
