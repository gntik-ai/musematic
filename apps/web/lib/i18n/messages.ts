import type { Locale } from "@/i18n.config";
import { DEFAULT_LOCALE } from "@/i18n.config";

export interface IntlMessages {
  [key: string]: string | IntlMessages;
}

const MESSAGE_LOADERS = {
  en: () => import("@/messages/en.json").then((module) => module.default),
  es: () => import("@/messages/es.json").then((module) => module.default),
  fr: () => import("@/messages/fr.json").then((module) => module.default),
  de: () => import("@/messages/de.json").then((module) => module.default),
  ja: () => import("@/messages/ja.json").then((module) => module.default),
  "zh-CN": () => import("@/messages/zh-CN.json").then((module) => module.default),
} satisfies Record<Locale, () => Promise<IntlMessages>>;

const ADMIN_MESSAGE_LOADERS = {
  en: () => import("@/messages/en/admin.json").then((module) => module.default),
  es: () => import("@/messages/es/admin.json").then((module) => module.default),
  fr: () => import("@/messages/fr/admin.json").then((module) => module.default),
  de: () => import("@/messages/de/admin.json").then((module) => module.default),
  ja: () => import("@/messages/ja/admin.json").then((module) => module.default),
  "zh-CN": () => import("@/messages/zh/admin.json").then((module) => module.default),
} satisfies Record<Locale, () => Promise<IntlMessages>>;

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function loadMessagesWithFallback(locale: Locale): Promise<IntlMessages> {
  const englishMessages = await loadCommittedMessages(DEFAULT_LOCALE);
  const runtimeMessages = await fetchRuntimeMessages(locale);
  const localizedMessages =
    runtimeMessages ?? (locale === DEFAULT_LOCALE ? englishMessages : await loadCommittedMessages(locale));
  return mergeMessages(englishMessages, localizedMessages);
}

async function loadCommittedMessages(locale: Locale): Promise<IntlMessages> {
  const [baseMessages, adminMessages] = await Promise.all([
    MESSAGE_LOADERS[locale](),
    ADMIN_MESSAGE_LOADERS[locale](),
  ]);
  return mergeMessages(baseMessages, { admin: adminMessages });
}

export function mergeMessages(
  fallbackMessages: IntlMessages,
  localizedMessages: IntlMessages,
): IntlMessages {
  const merged: IntlMessages = { ...fallbackMessages };
  for (const [key, value] of Object.entries(localizedMessages)) {
    const fallbackValue = fallbackMessages[key];
    if (isMessagesObject(fallbackValue) && isMessagesObject(value)) {
      merged[key] = mergeMessages(fallbackValue, value);
    } else {
      merged[key] = value;
    }
  }
  return merged;
}

function isMessagesObject(value: unknown): value is IntlMessages {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

async function fetchRuntimeMessages(locale: Locale): Promise<IntlMessages | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/locales/${locale}`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    const payload = (await response.json()) as { translations?: unknown };
    return isMessagesObject(payload.translations) ? payload.translations : null;
  } catch {
    return null;
  }
}
