import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { ClientErrorLogging } from "@/components/providers/ClientErrorLogging";
import { TenantBrandingProvider } from "@/components/features/shell/TenantBrandingProvider";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { WebSocketProvider } from "@/components/providers/WebSocketProvider";
import {
  LOCALE_COOKIE,
  THEME_COOKIE,
  normalizeLocale,
} from "@/i18n.config";
import { loadMessagesWithFallback } from "@/lib/i18n/messages";
import { getRequestLocale } from "@/lib/i18n/getRequestLocale";
import { Toaster } from "@/components/ui/toaster";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Musematic Agentic Mesh",
  description: "Operational frontend scaffold for the Agentic Mesh Platform.",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const requestHeaders = await headers();
  const cookieStore = await cookies();
  const locale = getRequestLocale({
    cookieLocale: cookieStore.get(LOCALE_COOKIE)?.value ?? null,
    acceptLanguage: requestHeaders.get("accept-language"),
  });
  const requestLocale = normalizeLocale(requestHeaders.get("x-musematic-locale"));
  const activeLocale = requestLocale ?? locale;
  const theme = requestHeaders.get("x-musematic-theme") ?? cookieStore.get(THEME_COOKIE)?.value;
  const themeClass = theme && theme !== "system" ? theme : undefined;
  const messages = await loadMessagesWithFallback(activeLocale);

  return (
    <html className={themeClass} lang={activeLocale} suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <ThemeProvider>
          <NextIntlClientProvider locale={activeLocale} messages={messages}>
            <QueryProvider>
              <WebSocketProvider>
                <ClientErrorLogging />
                <TenantBrandingProvider>{children}</TenantBrandingProvider>
                <Toaster />
              </WebSocketProvider>
            </QueryProvider>
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
