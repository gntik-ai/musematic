import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { WebSocketProvider } from "@/components/providers/WebSocketProvider";
import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  THEME_COOKIE,
  type Locale,
  normalizeLocale,
} from "@/i18n.config";
import { getRequestLocale } from "@/lib/i18n/getRequestLocale";
import { Toaster } from "@/components/ui/toaster";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: "Musematic Agentic Mesh",
  description: "Operational frontend scaffold for the Agentic Mesh Platform.",
};

const MESSAGE_LOADERS = {
  en: () => import("@/messages/en.json").then((module) => module.default),
  es: () => import("@/messages/es.json").then((module) => module.default),
  fr: () => import("@/messages/fr.json").then((module) => module.default),
  de: () => import("@/messages/de.json").then((module) => module.default),
  ja: () => import("@/messages/ja.json").then((module) => module.default),
  "zh-CN": () => import("@/messages/zh-CN.json").then((module) => module.default),
} satisfies Record<Locale, () => Promise<IntlMessages>>;

interface IntlMessages {
  [key: string]: string | IntlMessages;
}

async function loadMessages(locale: Locale) {
  return MESSAGE_LOADERS[locale]?.() ?? MESSAGE_LOADERS[DEFAULT_LOCALE]();
}

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
  const messages = await loadMessages(activeLocale);

  return (
    <html className={themeClass} lang={activeLocale} suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <ThemeProvider>
          <NextIntlClientProvider locale={activeLocale} messages={messages}>
            <QueryProvider>
              <WebSocketProvider>
                {children}
                <Toaster />
              </WebSocketProvider>
            </QueryProvider>
          </NextIntlClientProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
