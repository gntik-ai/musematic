"use client";

import { useTranslations } from "next-intl";

import { useConsentHistory } from "@/lib/hooks/use-me-consent";

function formatDate(value: string | null | undefined, emptyLabel: string): string {
  if (!value) {
    return emptyLabel;
  }
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
      new Date(value),
    );
  } catch {
    return value;
  }
}

export function ConsentHistoryTab() {
  const t = useTranslations("privacy.consent.history");
  const history = useConsentHistory();
  const items = history.data?.items ?? [];

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      {items.length === 0 ? (
        <div className="px-4 py-8 text-sm text-muted-foreground">{t("empty")}</div>
      ) : (
        items.map((item) => (
          <div key={item.id} className="border-b border-border px-4 py-3 text-sm last:border-b-0">
            <span className="font-medium">{item.consent_type}</span>
            <span className="ml-2 text-muted-foreground">
              {item.revoked_at
                ? t("revoked", { date: formatDate(item.revoked_at, t("never")) })
                : t("granted", { date: formatDate(item.granted_at, t("never")) })}
            </span>
          </div>
        ))
      )}
    </div>
  );
}
