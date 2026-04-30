"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Activity, KeyRound, ShieldCheck } from "lucide-react";

const securityLinks = [
  {
    href: "/settings/security/mfa",
    labelKey: "links.mfa.label",
    descriptionKey: "links.mfa.description",
    icon: ShieldCheck,
  },
  {
    href: "/settings/security/sessions",
    labelKey: "links.sessions.label",
    descriptionKey: "links.sessions.description",
    icon: KeyRound,
  },
  {
    href: "/settings/security/activity",
    labelKey: "links.activity.label",
    descriptionKey: "links.activity.description",
    icon: Activity,
  },
] as const;

export default function SecuritySettingsPage() {
  const t = useTranslations("security.overview");

  return (
    <div className="mx-auto w-full max-w-5xl space-y-5">
      <div className="flex items-center gap-3">
        <ShieldCheck className="h-6 w-6 text-brand-accent" />
        <div>
          <h1 className="text-2xl font-semibold">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        {securityLinks.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              className="rounded-lg border border-border bg-card p-4 text-card-foreground transition-colors hover:bg-accent"
              href={item.href}
            >
              <Icon className="mb-3 h-5 w-5 text-brand-accent" />
              <span className="block font-semibold">{t(item.labelKey)}</span>
              <span className="mt-1 block text-sm text-muted-foreground">
                {t(item.descriptionKey)}
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
