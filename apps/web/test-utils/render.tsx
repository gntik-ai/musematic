import type { PropsWithChildren, ReactElement } from "react";
import { render } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/query-client";
import { ThemeProvider } from "@/components/providers/ThemeProvider";

function Providers({ children }: PropsWithChildren): ReactElement {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </ThemeProvider>
  );
}

export function renderWithProviders(ui: ReactElement) {
  return render(ui, { wrapper: Providers });
}
