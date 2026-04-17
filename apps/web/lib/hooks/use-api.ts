"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type QueryFunctionContext,
  type QueryKey,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";

export function useAppQuery<TData>(
  key: QueryKey,
  fetcher: () => Promise<TData>,
  options?: Omit<UseQueryOptions<TData>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: key,
    queryFn: fetcher,
    staleTime: 30_000,
    gcTime: 300_000,
    retry: 1,
    ...options,
  });
}

export function useAppMutation<TData, TVariables>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  options?: UseMutationOptions<TData, Error, TVariables> & {
    invalidateKeys?: QueryKey[];
  },
) {
  const queryClient = useQueryClient();

  return useMutation({
    ...options,
    mutationFn,
    onSuccess: async (data, variables, onMutateResult, context) => {
      if (options?.invalidateKeys) {
        await Promise.all(
          options.invalidateKeys.map((queryKey) =>
            queryClient.invalidateQueries({ queryKey }),
          ),
        );
      }

      await options?.onSuccess?.(data, variables, onMutateResult, context);
    },
  });
}

interface AppInfiniteQueryOptions<TData, TCursor> {
  enabled?: boolean;
  getNextPageParam: (
    lastPage: TData,
    allPages: TData[],
  ) => TCursor | undefined;
  initialCursor?: TCursor;
}

export function useAppInfiniteQuery<TData, TCursor = string | null>(
  key: QueryKey,
  fetcher: (cursor: TCursor) => Promise<TData>,
  options: AppInfiniteQueryOptions<TData, TCursor>,
) {
  const queryOptions = {
    queryKey: key,
    initialPageParam: options.initialCursor as TCursor,
    queryFn: (context: QueryFunctionContext<QueryKey, TCursor>) =>
      fetcher(context.pageParam as TCursor),
    getNextPageParam: (lastPage: TData, allPages: TData[]) =>
      options.getNextPageParam(lastPage, allPages),
    staleTime: 30_000,
    gcTime: 300_000,
    retry: 1,
  } satisfies Parameters<
    typeof useInfiniteQuery<
      TData,
      Error,
      InfiniteData<TData, TCursor>,
      QueryKey,
      TCursor
    >
  >[0];

  if (options.enabled === undefined) {
    return useInfiniteQuery<TData, Error, InfiniteData<TData, TCursor>, QueryKey, TCursor>(
      queryOptions,
    );
  }

  return useInfiniteQuery<TData, Error, InfiniteData<TData, TCursor>, QueryKey, TCursor>({
    ...queryOptions,
    enabled: options.enabled,
  });
}
