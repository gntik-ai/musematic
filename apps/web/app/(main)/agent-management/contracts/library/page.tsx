"use client";

import { useTranslations } from "next-intl";
import { useContractTemplates } from "@/lib/hooks/use-contract-templates";
import { ForkDialog } from "./_components/ForkDialog";
import { TemplateCard } from "./_components/TemplateCard";

export default function ContractTemplateLibraryPage() {
  const t = useTranslations("creator.template");
  const templatesQuery = useContractTemplates();
  const templates = templatesQuery.data?.items ?? [];

  return (
    <section className="space-y-6">
      <div className="border-b pb-5">
        <p className="text-xs font-semibold uppercase text-brand-accent">{t("libraryEyebrow")}</p>
        <h1 className="mt-2 text-3xl font-semibold">{t("libraryTitle")}</h1>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {templates.map((template) => (
          <TemplateCard
            key={template.id}
            action={<ForkDialog templateId={template.id} templateName={template.name} />}
            template={template}
          />
        ))}
      </div>
    </section>
  );
}
