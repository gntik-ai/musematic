"use client";

import { fetchContractSchema } from "@/lib/api/creator-uis";
import { useAppQuery } from "@/lib/hooks/use-api";

export function useContractSchema() {
  return useAppQuery(["contract-schema"], fetchContractSchema, { staleTime: 3_600_000 });
}

