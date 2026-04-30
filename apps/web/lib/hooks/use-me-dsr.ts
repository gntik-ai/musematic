"use client";

import {
  fetchUserDsr,
  fetchUserDsrs,
  meQueryKeys,
  submitUserDsr,
} from "@/lib/api/me";
import { useAppInfiniteQuery, useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export function useUserDSRs(limit = 20) {
  return useAppInfiniteQuery(
    meQueryKeys.dsrs(null),
    (cursor: string | null) => fetchUserDsrs({ limit, cursor }),
    {
      initialCursor: null,
      getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    },
  );
}

export function useUserDSR(id: string | null) {
  return useAppQuery(meQueryKeys.dsr(id), () => fetchUserDsr(id ?? ""), {
    enabled: Boolean(id),
  });
}

export function useSubmitDSR() {
  return useAppMutation(submitUserDsr, {
    invalidateKeys: [meQueryKeys.dsrs(null)],
  });
}
