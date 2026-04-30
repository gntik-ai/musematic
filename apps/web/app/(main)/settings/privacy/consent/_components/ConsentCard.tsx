"use client";

import { useTranslations } from "next-intl";
import { ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { UserConsentItem } from "@/lib/schemas/me";
import { RevokeConsentDialog } from "./RevokeConsentDialog";

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

export function ConsentCard({ consent }: { consent: UserConsentItem }) {
  const t = useTranslations("privacy.consent.card");
  const active = consent.granted && !consent.revoked_at;

  return (
    <article className="rounded-lg border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <ShieldCheck className="mt-1 h-5 w-5 text-brand-accent" />
          <div>
            <h2 className="font-semibold">{consent.consent_type}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("grantedAt", { date: formatDate(consent.granted_at, t("never")) })}
            </p>
            {consent.revoked_at ? (
              <p className="mt-1 text-sm text-muted-foreground">
                {t("revokedAt", { date: formatDate(consent.revoked_at, t("never")) })}
              </p>
            ) : null}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={active ? "default" : "secondary"}>
            {active ? t("status.granted") : t("status.revoked")}
          </Badge>
          <RevokeConsentDialog consentType={consent.consent_type} disabled={!active} />
        </div>
      </div>
    </article>
  );
}
