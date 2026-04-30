"use client";

import { use, useMemo } from "react";
import { useTranslations } from "next-intl";

export default function ContractHistoryPage({ params }: { params: Promise<{ fqn: string }> }) {
  const t = useTranslations("creator.contract");
  const resolvedParams = use(params);
  const fqn = useMemo(() => decodeURIComponent(resolvedParams.fqn), [resolvedParams.fqn]);

  return (
    <section className="space-y-3">
      <p className="text-xs font-semibold uppercase text-brand-accent">{fqn}</p>
      <h1 className="text-3xl font-semibold">{t("history")}</h1>
      <p className="text-muted-foreground">{t("historyDescription")}</p>
    </section>
  );
}
