import type { OverallState } from "./status-client";

type Locale = "en" | "es" | "de" | "fr" | "it" | "zh-CN";

type Dictionary = {
  pageTitle: string;
  allSystemsOperational: string;
  subscribeToUpdates: string;
  lastUpdated: string;
  thirtyDayUptime: string;
  statusLabels: Record<OverallState, string>;
  activeIncidents: string;
  recentHistory: string;
  componentHistory: string;
  feedLinks: string;
  dataStale: string;
  noIncidents: string;
};

const en: Dictionary = {
  pageTitle: "Musematic Platform Status",
  allSystemsOperational: "All systems operational",
  subscribeToUpdates: "Subscribe to updates",
  lastUpdated: "Last updated",
  thirtyDayUptime: "30-day uptime",
  statusLabels: {
    operational: "Operational",
    degraded: "Degraded performance",
    partial_outage: "Partial outage",
    full_outage: "Full outage",
    maintenance: "Maintenance",
  },
  activeIncidents: "Active incidents",
  recentHistory: "Recent history",
  componentHistory: "Component history",
  feedLinks: "Feeds",
  dataStale: "Status data is stale",
  noIncidents: "No incidents in this window",
};

const dictionaries: Record<Locale, Dictionary> = {
  en,
  es: en,
  de: en,
  fr: en,
  it: en,
  "zh-CN": en,
};

export function resolveLocale(acceptLanguage?: string | null): Locale {
  if (!acceptLanguage) {
    return "en";
  }
  const requested = acceptLanguage
    .split(",")
    .map((part) => part.trim().split(";")[0]?.trim())
    .filter(Boolean);
  for (const locale of requested) {
    if (locale === "zh-CN" || locale?.toLowerCase() === "zh-cn") {
      return "zh-CN";
    }
    const base = locale?.slice(0, 2).toLowerCase();
    if (base && base in dictionaries && base !== "zh") {
      return base as Locale;
    }
  }
  return "en";
}

export function getDictionary(locale: Locale = "en"): Dictionary {
  return dictionaries[locale] ?? en;
}
