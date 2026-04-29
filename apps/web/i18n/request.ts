import { getRequestConfig } from "next-intl/server";
import { cookies, headers } from "next/headers";

import { LOCALE_COOKIE, normalizeLocale } from "@/i18n.config";
import { getRequestLocale } from "@/lib/i18n/getRequestLocale";
import { loadMessagesWithFallback } from "@/lib/i18n/messages";

export default getRequestConfig(async () => {
  const requestHeaders = await headers();
  const cookieStore = await cookies();
  const resolvedLocale = getRequestLocale({
    cookieLocale: cookieStore.get(LOCALE_COOKIE)?.value ?? null,
    acceptLanguage: requestHeaders.get("accept-language"),
  });
  const requestLocale = normalizeLocale(requestHeaders.get("x-musematic-locale"));
  const locale = requestLocale ?? resolvedLocale;

  return {
    locale,
    messages: await loadMessagesWithFallback(locale),
  };
});
