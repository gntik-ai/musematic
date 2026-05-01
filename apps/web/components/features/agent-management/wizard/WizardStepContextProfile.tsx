"use client";

import { useTranslations } from "next-intl";
import type { CompositionBlueprint } from "@/lib/types/agent-management";

export function WizardStepContextProfile({ blueprint }: { blueprint: CompositionBlueprint }) {
  const t = useTranslations("creator.wizard");
  const agent = blueprint.description || t("thisAgent");

  return (
    <section className="rounded-lg border p-5">
      <h2 className="text-xl font-semibold">{t("contextProfile")}</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {t("contextProfileDescription", { agent })}
      </p>
    </section>
  );
}
