"use client";

import type { PropsWithChildren } from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

export function ThemeProvider({ children }: PropsWithChildren) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      disableTransitionOnChange
      enableSystem
      storageKey="musematic-theme"
      themes={["light", "dark", "system", "high_contrast"]}
    >
      {children}
    </NextThemesProvider>
  );
}
