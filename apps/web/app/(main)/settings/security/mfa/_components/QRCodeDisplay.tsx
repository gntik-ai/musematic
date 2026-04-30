"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, Copy } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";

import { Button } from "@/components/ui/button";

interface QRCodeDisplayProps {
  provisioningUri: string;
  secret: string;
}

export function QRCodeDisplay({ provisioningUri, secret }: QRCodeDisplayProps) {
  const t = useTranslations("security.mfa.qr");
  const [copied, setCopied] = useState(false);

  async function copySecret() {
    await navigator.clipboard.writeText(secret);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,240px)_1fr]">
      <div className="flex items-center justify-center rounded-lg border border-border bg-background p-5">
        <QRCodeSVG
          aria-label={t("aria")}
          className="h-auto max-w-full"
          size={200}
          value={provisioningUri}
        />
      </div>
      <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-4">
        <div>
          <h3 className="text-sm font-semibold">{t("manualTitle")}</h3>
          <p className="text-sm text-muted-foreground">{t("manualDescription")}</p>
        </div>
        <code className="block break-all rounded-md border border-border bg-background px-3 py-2 font-mono text-sm">
          {secret}
        </code>
        <Button type="button" variant="outline" onClick={() => void copySecret()}>
          {copied ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          ) : (
            <Copy className="h-4 w-4" />
          )}
          {copied ? t("copied") : t("copy")}
        </Button>
      </div>
    </div>
  );
}
