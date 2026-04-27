"use client";

import { fetchProfileSchema } from "@/lib/api/creator-uis";
import { useAppQuery } from "@/lib/hooks/use-api";

export function useProfileSchema() {
  return useAppQuery(["context-profile-schema"], fetchProfileSchema, { staleTime: 3_600_000 });
}

