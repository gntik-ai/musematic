export type OverallState =
  | "operational"
  | "degraded"
  | "partial_outage"
  | "full_outage"
  | "maintenance";

export type ComponentStatus = {
  id: string;
  name: string;
  state: OverallState;
  last_check_at: string;
  uptime_30d_pct?: number | null;
};

export type PublicIncident = {
  id: string;
  title: string;
  severity: "info" | "warning" | "high" | "critical";
  started_at: string;
  resolved_at?: string | null;
  components_affected: string[];
  last_update_at: string;
  last_update_summary: string;
};

export type MaintenanceWindow = {
  window_id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  blocks_writes: boolean;
  components_affected: string[];
};

export type PlatformStatusSnapshot = {
  snapshot_id?: string | null;
  generated_at: string;
  overall_state: OverallState;
  components: ComponentStatus[];
  active_incidents: PublicIncident[];
  scheduled_maintenance: MaintenanceWindow[];
  active_maintenance?: MaintenanceWindow | null;
  recently_resolved_incidents: PublicIncident[];
  uptime_30d: Record<string, { pct: number; incidents: number }>;
  source_kind?: string;
};

export type SnapshotLoadResult = {
  snapshot: PlatformStatusSnapshot;
  source: "api" | "last-known-good" | "embedded";
  stale: boolean;
};

const FIVE_MINUTES_MS = 5 * 60 * 1000;

export const embeddedSnapshot: PlatformStatusSnapshot = {
  snapshot_id: "embedded-operational",
  generated_at: "2026-04-28T00:00:00.000Z",
  overall_state: "operational",
  components: [
    {
      id: "control-plane-api",
      name: "Control Plane API",
      state: "operational",
      last_check_at: "2026-04-28T00:00:00.000Z",
      uptime_30d_pct: 100,
    },
    {
      id: "web-app",
      name: "Authenticated Web App",
      state: "operational",
      last_check_at: "2026-04-28T00:00:00.000Z",
      uptime_30d_pct: 100,
    },
    {
      id: "reasoning-engine",
      name: "Reasoning Engine",
      state: "operational",
      last_check_at: "2026-04-28T00:00:00.000Z",
      uptime_30d_pct: 100,
    },
    {
      id: "workflow-engine",
      name: "Workflow Engine",
      state: "operational",
      last_check_at: "2026-04-28T00:00:00.000Z",
      uptime_30d_pct: 100,
    },
  ],
  active_incidents: [],
  scheduled_maintenance: [],
  active_maintenance: null,
  recently_resolved_incidents: [],
  uptime_30d: {},
  source_kind: "fallback",
};

export function isSnapshotStale(snapshot: PlatformStatusSnapshot): boolean {
  const generatedAt = Date.parse(snapshot.generated_at);
  if (Number.isNaN(generatedAt)) {
    return true;
  }
  return Date.now() - generatedAt > FIVE_MINUTES_MS;
}

export async function loadStatusSnapshot(): Promise<SnapshotLoadResult> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_STATUS_API_BASE_URL ?? "";
  try {
    const response = await fetch(`${apiBaseUrl}/api/v1/public/status`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`status_api_${response.status}`);
    }
    const snapshot = (await response.json()) as PlatformStatusSnapshot;
    return { snapshot, source: "api", stale: isSnapshotStale(snapshot) };
  } catch {
    return loadLastKnownGoodSnapshot();
  }
}

export async function loadLastKnownGoodSnapshot(): Promise<SnapshotLoadResult> {
  try {
    const response = await fetch("/last-known-good.json", {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error(`last_known_good_${response.status}`);
    }
    const snapshot = (await response.json()) as PlatformStatusSnapshot;
    return {
      snapshot,
      source: "last-known-good",
      stale: isSnapshotStale(snapshot),
    };
  } catch {
    return {
      snapshot: embeddedSnapshot,
      source: "embedded",
      stale: true,
    };
  }
}
