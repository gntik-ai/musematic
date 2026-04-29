export interface TagLabelFilters {
  tags: string[];
  labels: Record<string, string>;
}

export const EMPTY_TAG_LABEL_FILTERS: TagLabelFilters = {
  tags: [],
  labels: {},
};

type SearchParamSource = URLSearchParams | { toString: () => string };

function readCsv(value: string | null): string[] {
  if (!value) {
    return [];
  }

  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

function normalizeLabelMap(value: unknown): Record<string, string> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return {};
  }

  const labels: Record<string, string> = {};
  for (const [key, itemValue] of Object.entries(value)) {
    const labelKey = key.trim();
    if (labelKey) {
      labels[labelKey] = String(itemValue ?? "").trim();
    }
  }
  return labels;
}

function clearTagLabelParams(params: URLSearchParams): void {
  params.delete("tags");
  for (const key of Array.from(params.keys())) {
    if (key.startsWith("label.")) {
      params.delete(key);
    }
  }
}

export function parseTagLabelFilters(source: SearchParamSource): TagLabelFilters {
  const searchParams =
    source instanceof URLSearchParams ? source : new URLSearchParams(source.toString());
  const labels: Record<string, string> = {};

  for (const [key, value] of searchParams.entries()) {
    if (key.startsWith("label.")) {
      const labelKey = key.slice("label.".length).trim();
      if (labelKey) {
        labels[labelKey] = value.trim();
      }
    }
  }

  return {
    tags: readCsv(searchParams.get("tags")),
    labels,
  };
}

export function appendTagLabelFilters(
  params: URLSearchParams,
  filters: TagLabelFilters,
): void {
  if (filters.tags.length > 0) {
    params.set("tags", filters.tags.join(","));
  }

  for (const [key, value] of Object.entries(filters.labels)) {
    if (key.trim() && value.trim()) {
      params.set(`label.${key.trim()}`, value.trim());
    }
  }
}

export function writeTagLabelFilters(
  source: SearchParamSource,
  filters: TagLabelFilters,
): URLSearchParams {
  const params = new URLSearchParams(source.toString());
  clearTagLabelParams(params);
  appendTagLabelFilters(params, filters);
  return params;
}

export function extractTagLabelFilters(filters: Record<string, unknown>): TagLabelFilters {
  const labels = {
    ...normalizeLabelMap(filters.label),
    ...normalizeLabelMap(filters.labels),
  };

  for (const [key, value] of Object.entries(filters)) {
    if (key.startsWith("label.")) {
      const labelKey = key.slice("label.".length).trim();
      if (labelKey) {
        labels[labelKey] = String(value ?? "").trim();
      }
    }
  }

  return {
    tags: Array.isArray(filters.tags)
      ? filters.tags.map((item) => String(item).trim()).filter(Boolean)
      : [],
    labels,
  };
}

function writeFilterValue(params: URLSearchParams, key: string, value: unknown): void {
  params.delete(key);
  if (value === null || value === undefined || value === "") {
    return;
  }
  if (Array.isArray(value)) {
    const normalized = value.map((entry) => String(entry).trim()).filter(Boolean);
    if (normalized.length > 0) {
      params.set(key, normalized.join(","));
    }
    return;
  }
  params.set(key, String(value));
}

export function savedViewFiltersToSearchParams(
  current: SearchParamSource,
  filters: Record<string, unknown>,
  clearKeys: string[] = [],
): URLSearchParams {
  const params = new URLSearchParams(current.toString());
  clearTagLabelParams(params);
  clearKeys.forEach((key) => params.delete(key));

  for (const [key, value] of Object.entries(filters)) {
    if (key === "tags") {
      writeFilterValue(params, "tags", value);
      continue;
    }
    if (key === "labels" || key === "label") {
      for (const [labelKey, labelValue] of Object.entries(normalizeLabelMap(value))) {
        writeFilterValue(params, `label.${labelKey}`, labelValue);
      }
      continue;
    }
    writeFilterValue(params, key, value);
  }

  return params;
}

export function tagLabelFiltersForSavedView(
  filters: TagLabelFilters,
): Record<string, unknown> {
  return {
    tags: filters.tags,
    labels: filters.labels,
  };
}
