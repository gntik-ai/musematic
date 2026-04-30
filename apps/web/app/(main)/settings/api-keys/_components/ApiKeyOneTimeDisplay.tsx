"use client";

import { useTranslations } from "next-intl";
import { Copy, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";

interface ApiKeyOneTimeDisplayProps {
  tokenValue: string;
  onDismiss: () => void;
}

export function ApiKeyOneTimeDisplay({ tokenValue, onDismiss }: ApiKeyOneTimeDisplayProps) {
  const t = useTranslations("apiKeys.oneTime");

  async function copyToken() {
    await navigator.clipboard.writeText(tokenValue);
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-4">
      <div>
        <h3 className="text-sm font-semibold">{t("title")}</h3>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </div>
      <pre className="overflow-x-auto rounded-md border border-border bg-background p-3 text-sm">
        <code>{tokenValue}</code>
      </pre>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={copyToken}>
          <Copy className="h-4 w-4" />
          {t("copy")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDismiss}>
          <EyeOff className="h-4 w-4" />
          {t("dismiss")}
        </Button>
      </div>
    </div>
  );
}
