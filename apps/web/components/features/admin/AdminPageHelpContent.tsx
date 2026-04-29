"use client";

import { useTranslations } from "next-intl";

interface AdminPageHelpContentProps {
  pageKey: string;
}

export function AdminPageHelpContent({ pageKey }: AdminPageHelpContentProps) {
  const t = useTranslations(`admin.help.${pageKey}`);

  return (
    <div className="space-y-3">
      <p>{t("summary")}</p>
      <ul className="list-disc space-y-1 pl-4">
        <li>{t("scope")}</li>
        <li>{t("safety")}</li>
      </ul>
    </div>
  );
}
