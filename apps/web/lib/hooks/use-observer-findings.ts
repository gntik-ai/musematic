"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAppQuery } from "@/lib/hooks/use-api";
import { fleetApi, fleetQueryKeys } from "@/lib/hooks/use-fleets";
import type {
  AcknowledgeFindingInput,
  ObserverFinding,
  ObserverFindingFilters,
} from "@/lib/types/fleet";

interface ObserverFindingsResponse {
  items: ObserverFinding[];
  next_cursor: string | null;
}

function buildObserverFindingsPath(
  fleetId: string,
  filters: ObserverFindingFilters,
): string {
  const searchParams = new URLSearchParams({
    limit: String(filters.limit ?? 100),
  });

  if (filters.cursor) {
    searchParams.set("cursor", filters.cursor);
  }
  if (filters.severity) {
    searchParams.set("severity", filters.severity);
  }
  if (filters.acknowledged !== null) {
    searchParams.set("acknowledged", String(filters.acknowledged));
  }

  return `/api/v1/fleets/${encodeURIComponent(fleetId)}/observer-findings?${searchParams.toString()}`;
}

export function useObserverFindings(
  fleetId: string | null | undefined,
  filters: ObserverFindingFilters,
) {
  return useAppQuery<ObserverFindingsResponse>(
    fleetQueryKeys.observerFindings(fleetId, filters),
    () =>
      fleetApi.get<ObserverFindingsResponse>(
        buildObserverFindingsPath(fleetId ?? "", filters),
      ),
    {
      enabled: Boolean(fleetId),
    },
  );
}

export function useAcknowledgeFinding() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ fleetId, findingId }: AcknowledgeFindingInput) =>
      fleetApi.post<ObserverFinding>(
        `/api/v1/fleets/${encodeURIComponent(fleetId)}/observer-findings/${encodeURIComponent(findingId)}/acknowledge`,
      ),
    onMutate: async (variables) => {
      const queryEntries = queryClient.getQueriesData<ObserverFindingsResponse>({
        queryKey: ["fleet", "observer-findings", variables.fleetId],
      });

      await Promise.all(
        queryEntries.map(([queryKey]) =>
          queryClient.cancelQueries({ queryKey }),
        ),
      );

      const snapshots = queryEntries.map(([queryKey, value]) => [queryKey, value] as const);

      for (const [queryKey, value] of queryEntries) {
        if (!value) {
          continue;
        }

        queryClient.setQueryData<ObserverFindingsResponse>(queryKey, {
          ...value,
          items: value.items.map((item) =>
            item.id === variables.findingId
              ? {
                  ...item,
                  acknowledged: true,
                  acknowledged_at: new Date().toISOString(),
                }
              : item,
          ),
        });
      }

      return { snapshots };
    },
    onError: (_error, _variables, context) => {
      context?.snapshots.forEach(([queryKey, value]) => {
        queryClient.setQueryData(queryKey, value);
      });
    },
    onSettled: async (_data, _error, variables) => {
      await queryClient.invalidateQueries({
        queryKey: ["fleet", "observer-findings", variables.fleetId],
      });
    },
  });
}

