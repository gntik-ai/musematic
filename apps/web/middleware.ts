import { type NextRequest, NextResponse } from "next/server";
import { LOCALE_COOKIE, THEME_COOKIE, normalizeLocale, resolveLocale } from "@/i18n.config";

const THEMES = new Set(["light", "dark", "system", "high_contrast"]);

export function middleware(request: NextRequest) {
  const urlHint = request.nextUrl.searchParams.get("lang");
  const cookieLocale = request.cookies.get(LOCALE_COOKIE)?.value ?? null;
  const acceptLanguage = request.headers.get("accept-language");
  const locale = resolveLocale({
    urlHint,
    userPreference: cookieLocale,
    acceptLanguage,
  });

  const rawTheme = request.cookies.get(THEME_COOKIE)?.value;
  const theme = rawTheme && THEMES.has(rawTheme) ? rawTheme : "system";
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-musematic-locale", normalizeLocale(urlHint) ?? locale);
  requestHeaders.set("x-musematic-theme", theme);

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
  response.cookies.set(LOCALE_COOKIE, locale, {
    httpOnly: false,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
  });
  response.cookies.set(THEME_COOKIE, theme, {
    httpOnly: false,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
  });
  return response;
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|icons).*)"],
};
