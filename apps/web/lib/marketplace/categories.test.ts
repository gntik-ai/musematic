/**
 * UPD-049 — Sanity test for the marketing-category mirror.
 *
 * The full backend-vs-frontend parity check (T038) lives in CI as a
 * cross-language script; this test guards basic invariants of the TS
 * mirror so a typo or duplicate in the constant fails fast.
 */

import { describe, expect, it } from "vitest";
import {
  MARKETING_CATEGORIES,
  MARKETING_CATEGORY_LABELS,
} from "@/lib/marketplace/categories";

describe("MARKETING_CATEGORIES", () => {
  it("has the expected 10 platform-curated entries", () => {
    expect(MARKETING_CATEGORIES).toHaveLength(10);
  });

  it("has no duplicate slugs", () => {
    const set = new Set(MARKETING_CATEGORIES);
    expect(set.size).toBe(MARKETING_CATEGORIES.length);
  });

  it("ends with the 'other' catch-all (UX ordering invariant)", () => {
    expect(MARKETING_CATEGORIES[MARKETING_CATEGORIES.length - 1]).toBe("other");
  });

  it("provides a label for every category", () => {
    for (const category of MARKETING_CATEGORIES) {
      expect(MARKETING_CATEGORY_LABELS[category]).toBeTruthy();
    }
  });
});
