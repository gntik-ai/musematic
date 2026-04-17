import type { PropsWithChildren, ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export function createHookWrapper(client = createTestQueryClient()) {
  const Wrapper = ({ children }: PropsWithChildren): ReactNode => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

  return { client, Wrapper };
}
