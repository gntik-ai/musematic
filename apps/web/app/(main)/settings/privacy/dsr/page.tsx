"use client";

import { useTranslations } from "next-intl";
import { FileText } from "lucide-react";

import { useUserDSRs } from "@/lib/hooks/use-me-dsr";
import { DsrStatusList } from "./_components/DsrStatusList";
import { DsrSubmissionForm } from "./_components/DsrSubmissionForm";

export default function DsrPage() {
  const t = useTranslations("privacy.dsr");
  const dsrs = useUserDSRs();
  const items = dsrs.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="mx-auto w-full max-w-6xl space-y-5">
      <div className="flex items-center gap-3">
        <FileText className="h-6 w-6 text-brand-accent" />
        <div>
          <h1 className="text-2xl font-semibold">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-[360px_1fr]">
        <DsrSubmissionForm />
        <DsrStatusList items={items} />
      </div>
    </div>
  );
}
