"use client";

import { ApiError } from "@/types/api";
import { createApiClient } from "@/lib/api";
import { useAppQuery } from "@/lib/hooks/use-api";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";
import { appendTagLabelFilters } from "@/lib/tagging/filter-query";
import type {
  CertificationDetail,
  CertificationListEntry,
  CertificationQueueFilters,
  CertificationStatus,
  CertificationStatusEvent,
  EvidenceItem,
  EvidenceResult,
  EvidenceType,
} from "@/lib/types/trust-workbench";

export const trustWorkbenchApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface CertificationQueueResponse {
  items: CertificationListEntry[];
  total: number;
  page: number;
  pageSize: number;
}

interface QueueApiResponse {
  items?: unknown[];
  total?: number;
  page?: number;
  page_size?: number;
  pageSize?: number;
}

interface DetailApiResponse extends Record<string, unknown> {
  evidenceRefs?: unknown[];
  evidence_refs?: unknown[];
  evidenceItems?: unknown[];
  evidence_items?: unknown[];
  statusHistory?: unknown[];
  status_history?: unknown[];
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asEvidenceType(value: unknown): EvidenceType {
  const allowed: EvidenceType[] = [
    "package_validation",
    "test_results",
    "policy_check",
    "guardrail_outcomes",
    "behavioral_regression",
    "ate_results",
    "manual_review",
  ];

  return allowed.includes(value as EvidenceType)
    ? (value as EvidenceType)
    : "manual_review";
}

export function deriveEvidenceResult(
  summary: string | null,
  evidenceType: EvidenceType,
): EvidenceResult {
  const normalized = summary?.toLowerCase() ?? "";
  if (normalized.includes("partial")) {
    return "partial";
  }
  if (
    normalized.includes("fail") ||
    normalized.includes("denied") ||
    normalized.includes("blocked")
  ) {
    return "fail";
  }
  if (
    normalized.includes("pass") ||
    normalized.includes("approved") ||
    normalized.includes("success")
  ) {
    return "pass";
  }
  if (evidenceType === "policy_check") {
    return "partial";
  }

  return "unknown";
}

function asCertificationStatus(value: unknown): CertificationStatus {
  const allowed: CertificationStatus[] = [
    "pending",
    "active",
    "expired",
    "revoked",
    "superseded",
  ];

  return allowed.includes(value as CertificationStatus)
    ? (value as CertificationStatus)
    : "pending";
}

function normalizeEvidenceItem(raw: unknown): EvidenceItem {
  const entry = asRecord(raw);
  const evidenceType = asEvidenceType(
    entry.evidenceType ?? entry.evidence_type ?? entry.type,
  );
  const summary = asNullableString(entry.summary);

  return {
    id: asString(entry.id, crypto.randomUUID()),
    evidenceType,
    sourceRefType: asString(entry.sourceRefType ?? entry.source_ref_type),
    sourceRefId: asString(entry.sourceRefId ?? entry.source_ref_id),
    summary,
    storageRef: asNullableString(entry.storageRef ?? entry.storage_ref),
    createdAt: asString(
      entry.createdAt ?? entry.created_at,
      new Date(0).toISOString(),
    ),
    result: deriveEvidenceResult(summary, evidenceType),
  };
}

function buildStatusHistory(
  raw: DetailApiResponse,
  fallbackStatus: CertificationStatus,
): CertificationStatusEvent[] {
  const history = (raw.statusHistory ??
    raw.status_history) as unknown[] | undefined;

  if (Array.isArray(history) && history.length > 0) {
    return history.map((item, index) => {
      const entry = asRecord(item);

      return {
        id: asString(entry.id, `status-${index}`),
        status: asCertificationStatus(entry.status),
        timestamp: asString(
          entry.timestamp ?? entry.createdAt ?? entry.created_at,
          new Date(0).toISOString(),
        ),
        actor: asString(
          entry.actor ?? entry.actorUsername ?? entry.actor_username,
          "System",
        ),
        notes: asNullableString(entry.notes),
      };
    });
  }

  const createdAt = asString(raw.createdAt ?? raw.created_at, new Date(0).toISOString());
  const updatedAt = asString(raw.updatedAt ?? raw.updated_at, createdAt);
  const events: CertificationStatusEvent[] = [
    {
      id: "created",
      status: "pending",
      timestamp: createdAt,
      actor: asString(raw.issuedBy ?? raw.issued_by, "System"),
      notes: null,
    },
  ];

  if (fallbackStatus !== "pending" || updatedAt !== createdAt) {
    events.push({
      id: "current",
      status: fallbackStatus,
      timestamp: updatedAt,
      actor: asString(raw.updatedBy ?? raw.updated_by, "Reviewer"),
      notes: asNullableString(raw.revocationReason ?? raw.revocation_reason),
    });
  }

  return events.sort(
    (left, right) =>
      new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime(),
  );
}

function normalizeCertificationListEntry(raw: unknown): CertificationListEntry {
  const entry = asRecord(raw);
  const evidenceRefs = Array.isArray(entry.evidenceRefs ?? entry.evidence_refs)
    ? ((entry.evidenceRefs ?? entry.evidence_refs) as unknown[])
    : [];
  const evidenceCount =
    typeof entry.evidenceCount === "number"
      ? entry.evidenceCount
      : typeof entry.evidence_count === "number"
        ? (entry.evidence_count as number)
        : evidenceRefs.length;
  const entityName = asString(
    entry.entityName ?? entry.entity_name ?? entry.fleetName ?? entry.fleet_name ?? entry.agentName ?? entry.agent_name,
    asString(entry.agentFqn ?? entry.agent_fqn),
  );
  const entityFqn = asString(
    entry.entityFqn ?? entry.entity_fqn ?? entry.agentFqn ?? entry.agent_fqn,
    entityName,
  );
  const entityType =
    (entry.entityType ?? entry.entity_type ?? (entry.fleetId || entry.fleet_id ? "fleet" : "agent")) ===
    "fleet"
      ? "fleet"
      : "agent";

  return {
    id: asString(entry.id),
    agentId: asString(entry.agentId ?? entry.agent_id),
    agentFqn: asString(entry.agentFqn ?? entry.agent_fqn, entityFqn),
    agentRevisionId: asString(entry.agentRevisionId ?? entry.agent_revision_id),
    entityName,
    entityFqn,
    entityType,
    certificationType: asString(
      entry.certificationType ?? entry.certification_type,
      "trust_review",
    ),
    status: asCertificationStatus(entry.status),
    issuedBy: asString(entry.issuedBy ?? entry.issued_by, "System"),
    createdAt: asString(
      entry.createdAt ?? entry.created_at,
      new Date(0).toISOString(),
    ),
    updatedAt: asString(
      entry.updatedAt ?? entry.updated_at,
      new Date(0).toISOString(),
    ),
    expiresAt: asNullableString(entry.expiresAt ?? entry.expires_at),
    revokedAt: asNullableString(entry.revokedAt ?? entry.revoked_at),
    revocationReason: asNullableString(
      entry.revocationReason ?? entry.revocation_reason,
    ),
    evidenceCount,
    fleetId: asNullableString(entry.fleetId ?? entry.fleet_id) ?? undefined,
    fleetName:
      asNullableString(entry.fleetName ?? entry.fleet_name) ?? undefined,
  };
}

function normalizeCertificationDetail(raw: unknown): CertificationDetail {
  const entry = asRecord(raw) as DetailApiResponse;
  const listEntry = normalizeCertificationListEntry(entry);
  const evidenceItemsRaw =
    (entry.evidenceItems ??
      entry.evidence_items ??
      entry.evidenceRefs ??
      entry.evidence_refs) as unknown[] | undefined;
  const evidenceItems = Array.isArray(evidenceItemsRaw)
    ? evidenceItemsRaw.map(normalizeEvidenceItem)
    : [];

  return {
    ...listEntry,
    supersededById: asNullableString(
      entry.supersededById ?? entry.superseded_by_id,
    ),
    evidenceItems,
    statusHistory: buildStatusHistory(entry, listEntry.status),
  };
}

export const certificationQueryKeys = {
  root: ["certificationQueue"] as const,
  queue: (filters: CertificationQueueFilters) =>
    ["certificationQueue", filters] as const,
  detail: (certificationId: string | null | undefined) =>
    ["certification", certificationId ?? "none"] as const,
};

function buildQueuePath(filters: CertificationQueueFilters): string {
  const searchParams = new URLSearchParams({
    sort_by: filters.sort_by,
    page: String(filters.page),
    page_size: String(filters.page_size),
  });

  if (filters.status) {
    searchParams.set("status", filters.status);
  }
  if (filters.search) {
    searchParams.set("search", filters.search);
  }
  appendTagLabelFilters(searchParams, {
    tags: filters.tags,
    labels: filters.labels,
  });

  return `/api/v1/trust/certifications?${searchParams.toString()}`;
}

export function useCertificationQueue(filters: CertificationQueueFilters) {
  const debouncedSearch = useDebouncedValue(filters.search, 300);
  const resolvedFilters: CertificationQueueFilters = {
    ...filters,
    search: debouncedSearch,
  };

  return useAppQuery<CertificationQueueResponse>(
    certificationQueryKeys.queue(resolvedFilters),
    async () => {
      const response = await trustWorkbenchApi.get<QueueApiResponse>(
        buildQueuePath(resolvedFilters),
      );

      return {
        items: (response.items ?? []).map(normalizeCertificationListEntry),
        total: response.total ?? 0,
        page: response.page ?? resolvedFilters.page,
        pageSize:
          response.pageSize ?? response.page_size ?? resolvedFilters.page_size,
      };
    },
  );
}

export function useCertification(certificationId: string | null | undefined) {
  return useAppQuery<CertificationDetail>(
    certificationQueryKeys.detail(certificationId),
    async () => {
      try {
        const response = await trustWorkbenchApi.get<DetailApiResponse>(
          `/api/v1/trust/certifications/${encodeURIComponent(certificationId ?? "")}`,
        );

        return normalizeCertificationDetail(response);
      } catch (error) {
        if (error instanceof ApiError) {
          throw error;
        }
        throw error;
      }
    },
    {
      enabled: Boolean(certificationId),
    },
  );
}
