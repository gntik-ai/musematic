"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { OAuthProviderSource } from "@/lib/types/oauth";

const sourceClassNames: Record<OAuthProviderSource, string> = {
  env_var: "border-blue-200 bg-blue-50 text-blue-700",
  manual: "border-slate-200 bg-slate-50 text-slate-700",
  imported: "border-violet-200 bg-violet-50 text-violet-700",
};

export function OAuthProviderSourceBadge({
  source,
}: {
  source: OAuthProviderSource;
}) {
  const t = useTranslations("admin.oauth");

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Badge
            aria-label={t("source.aria", { source: t(`source.${source}`) })}
            className={sourceClassNames[source]}
            variant="outline"
          >
            {t(`source.${source}`)}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{t(`source.${source}Help`)}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
