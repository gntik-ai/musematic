"use client";

import { useMemo } from "react";
import { useCertificationQueue } from "@/lib/hooks/use-certifications";

export type CertificationExpirySort = "expires_at_asc" | "agent_fqn" | "certifier_name";

export interface CertificationExpiryRow {
  id: string;
  agentFqn: string;
  certifierName: string;
  issuedAt: string;
  expiresAt: string | null;
  status: "green" | "amber" | "red";
}

export function useCertificationExpiries(sort: CertificationExpirySort) {
  const queue = useCertificationQueue({
    status: null,
    search: "",
    tags: [],
    labels: {},
    sort_by: "expiration",
    page: 1,
    page_size: 100,
  });

  const items = useMemo(() => {
    const mapped = (queue.data?.items ?? []).map((item) => ({
      id: item.id,
      agentFqn: item.agentFqn,
      certifierName: item.issuedBy,
      issuedAt: item.createdAt,
      expiresAt: item.expiresAt,
      status:
        item.status === "revoked" || item.status === "expired"
          ? "red"
          : item.status === "pending"
            ? "amber"
            : "green",
    } satisfies CertificationExpiryRow));

    return mapped.sort((left, right) => {
      if (sort === "agent_fqn") {
        return left.agentFqn.localeCompare(right.agentFqn);
      }
      if (sort === "certifier_name") {
        return left.certifierName.localeCompare(right.certifierName);
      }
      return (left.expiresAt ?? "9999-12-31").localeCompare(right.expiresAt ?? "9999-12-31");
    });
  }, [queue.data?.items, sort]);

  return {
    ...queue,
    items,
  };
}
