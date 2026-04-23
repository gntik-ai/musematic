"use client";

import { createApiClient } from "@/lib/api";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";
import type { ThirdPartyCertifier } from "@/types/operator";

const trustApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function normalizeCertifier(raw: unknown): ThirdPartyCertifier {
  const item = asRecord(raw);
  const credentials = asRecord(item.credentials);
  return {
    id: asString(item.id),
    displayName: asString(item.name),
    endpoint: asString(credentials.endpoint, "https://example.invalid"),
    scope: Array.isArray(item.permitted_scopes) ? item.permitted_scopes.map(String) : [],
    publicKeyFingerprint: asString(credentials.public_key_fingerprint, null as never) || null,
  };
}

export interface CertifierFormInput {
  displayName: string;
  endpoint: string;
  publicKeyPem: string;
  scope: string;
}

export function useThirdPartyCertifiers() {
  const query = useAppQuery<{ items: ThirdPartyCertifier[]; total: number }>(
    ["certifiers"],
    async () => {
      const response = await trustApi.get<{ items?: unknown[]; total?: number }>("/api/v1/trust/certifiers");
      return {
        items: (response.items ?? []).map(normalizeCertifier),
        total: response.total ?? 0,
      };
    },
  );

  return {
    ...query,
    certifiers: query.data?.items ?? [],
  };
}

export function useCertifierMutations() {
  const createCertifier = useAppMutation<ThirdPartyCertifier, CertifierFormInput>(
    async (input) => {
      const created = await trustApi.post<Record<string, unknown>>("/api/v1/trust/certifiers", {
        name: input.displayName,
        organization: null,
        permitted_scopes: [input.scope],
        credentials: {
          endpoint: input.endpoint,
          public_key_pem: input.publicKeyPem,
          public_key_fingerprint: input.publicKeyPem.slice(0, 24),
        },
      });
      return normalizeCertifier(created);
    },
    {
      invalidateKeys: [["certifiers"]],
    },
  );

  const deleteCertifier = useAppMutation<void, { certifierId: string }>(
    async ({ certifierId }) => {
      await trustApi.delete(`/api/v1/trust/certifiers/${encodeURIComponent(certifierId)}`);
    },
    {
      invalidateKeys: [["certifiers"]],
    },
  );

  return {
    createCertifier,
    deleteCertifier,
  };
}
