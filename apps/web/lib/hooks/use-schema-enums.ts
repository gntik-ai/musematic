"use client";

import { fetchContractSchemaEnums } from "@/lib/api/creator-uis";
import { useAppQuery } from "@/lib/hooks/use-api";

export function useSchemaEnums() {
  return useAppQuery(["contract-schema-enums"], fetchContractSchemaEnums, {
    staleTime: 3_600_000,
  });
}

