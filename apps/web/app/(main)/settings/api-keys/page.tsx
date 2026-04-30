"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { KeyRound } from "lucide-react";

import { ApiKeyCreateDialog } from "./_components/ApiKeyCreateDialog";
import { ApiKeyOneTimeDisplay } from "./_components/ApiKeyOneTimeDisplay";
import { ApiKeyTable } from "./_components/ApiKeyTable";
import { useUserApiKeys } from "@/lib/hooks/use-me-api-keys";
import type { UserServiceAccountCreateResponse } from "@/lib/schemas/me";

export default function ApiKeysPage() {
  const t = useTranslations("apiKeys");
  const apiKeys = useUserApiKeys();
  const [created, setCreated] = useState<UserServiceAccountCreateResponse | null>(null);
  const items = apiKeys.data?.items ?? [];
  const activeCount = items.filter((item) => item.status === "active").length;
  const maxActive = apiKeys.data?.max_active ?? 10;
  const atLimit = activeCount >= maxActive;

  return (
    <div className="mx-auto w-full max-w-6xl space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <KeyRound className="h-6 w-6 text-brand-accent" />
          <div>
            <h1 className="text-2xl font-semibold">{t("title")}</h1>
            <p className="text-sm text-muted-foreground">
              {t("description")}
            </p>
          </div>
        </div>
        <ApiKeyCreateDialog disabled={atLimit || apiKeys.isLoading} onCreated={setCreated} />
      </div>

      {created ? (
        <ApiKeyOneTimeDisplay tokenValue={created.api_key} onDismiss={() => setCreated(null)} />
      ) : null}

      <div className="rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
        {t("usage", { activeCount, maxActive })}
      </div>

      <ApiKeyTable items={items} />
    </div>
  );
}
