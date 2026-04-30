"use client";

import { fetchUserActivity, meQueryKeys, type UserActivityFilters } from "@/lib/api/me";
import { useAppInfiniteQuery } from "@/lib/hooks/use-api";

export function useUserActivity(filters: UserActivityFilters = {}) {
  return useAppInfiniteQuery(
    meQueryKeys.activity(filters),
    (cursor: string | null) => fetchUserActivity(filters, cursor),
    {
      initialCursor: null,
      getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    },
  );
}
