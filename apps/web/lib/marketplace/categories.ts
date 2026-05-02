/**
 * UPD-049 — frontend mirror of the platform-curated marketing-category list.
 *
 * MUST stay in lockstep with the backend constant at
 * `apps/control-plane/src/platform/marketplace/categories.py:MARKETING_CATEGORIES`.
 *
 * The CI parity check (T038) imports both lists and asserts equality so a
 * drift breaks the build.
 */

export const MARKETING_CATEGORIES = [
  "data-extraction",
  "summarisation",
  "code-assistance",
  "research",
  "automation",
  "communication",
  "analytics",
  "content-generation",
  "translation",
  "other",
] as const;

export type MarketingCategory = (typeof MARKETING_CATEGORIES)[number];

/** Human-readable labels for the marketing-category enum. Used in the
 *  publish-flow Select and the marketplace search facet. */
export const MARKETING_CATEGORY_LABELS: Record<MarketingCategory, string> = {
  "data-extraction": "Data extraction",
  summarisation: "Summarisation",
  "code-assistance": "Code assistance",
  research: "Research",
  automation: "Automation",
  communication: "Communication",
  analytics: "Analytics",
  "content-generation": "Content generation",
  translation: "Translation",
  other: "Other",
};
