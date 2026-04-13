import type { PropsWithChildren, ReactElement } from "react";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/providers/ThemeProvider";

function createTestQueryClient() {
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

function Providers({
  children,
  client,
}: PropsWithChildren<{ client: QueryClient }>): ReactElement {
  return (
    <ThemeProvider>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
}

export function renderWithProviders(ui: ReactElement) {
  const client = createTestQueryClient();

  return render(ui, {
    wrapper: ({ children }) => <Providers client={client}>{children}</Providers>,
  });
}
