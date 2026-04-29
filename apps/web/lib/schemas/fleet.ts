import type {
  FleetListFilters,
  FleetStatus,
  FleetTopologyType,
} from "@/lib/types/fleet";
import { DEFAULT_FLEET_LIST_FILTERS } from "@/lib/types/fleet";
import { appendTagLabelFilters, parseTagLabelFilters } from "@/lib/tagging/filter-query";

function parseMultiValue<T extends string>(value: string | null): T[] {
  if (!value) {
    return [];
  }

  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean) as T[];
}

export function parseFleetListFilters(searchParams: URLSearchParams): FleetListFilters {
  return {
    search: searchParams.get("search") ?? DEFAULT_FLEET_LIST_FILTERS.search,
    topology_type: parseMultiValue<FleetTopologyType>(searchParams.get("topology_type")),
    status: parseMultiValue<FleetStatus>(searchParams.get("status")),
    ...parseTagLabelFilters(searchParams),
    health_min: searchParams.get("health_min")
      ? Number(searchParams.get("health_min"))
      : DEFAULT_FLEET_LIST_FILTERS.health_min,
    sort_by:
      (searchParams.get("sort_by") as FleetListFilters["sort_by"] | null) ??
      DEFAULT_FLEET_LIST_FILTERS.sort_by,
    sort_order:
      (searchParams.get("sort_order") as FleetListFilters["sort_order"] | null) ??
      DEFAULT_FLEET_LIST_FILTERS.sort_order,
    page: searchParams.get("page")
      ? Number(searchParams.get("page"))
      : DEFAULT_FLEET_LIST_FILTERS.page,
    size: searchParams.get("size")
      ? Number(searchParams.get("size"))
      : DEFAULT_FLEET_LIST_FILTERS.size,
  };
}

export function serializeFleetListFilters(filters: FleetListFilters): URLSearchParams {
  const searchParams = new URLSearchParams();

  if (filters.search) {
    searchParams.set("search", filters.search);
  }
  if (filters.topology_type.length > 0) {
    searchParams.set("topology_type", filters.topology_type.join(","));
  }
  if (filters.status.length > 0) {
    searchParams.set("status", filters.status.join(","));
  }
  appendTagLabelFilters(searchParams, {
    tags: filters.tags,
    labels: filters.labels,
  });
  if (filters.health_min !== null) {
    searchParams.set("health_min", String(filters.health_min));
  }
  if (filters.sort_by !== DEFAULT_FLEET_LIST_FILTERS.sort_by) {
    searchParams.set("sort_by", filters.sort_by);
  }
  if (filters.sort_order !== DEFAULT_FLEET_LIST_FILTERS.sort_order) {
    searchParams.set("sort_order", filters.sort_order);
  }
  if (filters.page !== DEFAULT_FLEET_LIST_FILTERS.page) {
    searchParams.set("page", String(filters.page));
  }
  if (filters.size !== DEFAULT_FLEET_LIST_FILTERS.size) {
    searchParams.set("size", String(filters.size));
  }

  return searchParams;
}
