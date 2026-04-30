"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, Copy, Download, EyeOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

interface BackupCodesDisplayProps {
  codes: string[];
  onDismiss: () => void;
}

export function BackupCodesDisplay({ codes, onDismiss }: BackupCodesDisplayProps) {
  const t = useTranslations("security.mfa.backupCodes");
  const [acknowledged, setAcknowledged] = useState(false);
  const [copied, setCopied] = useState(false);
  const serializedCodes = useMemo(() => codes.join("\n"), [codes]);

  async function copyCodes() {
    await navigator.clipboard.writeText(serializedCodes);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  function downloadCodes() {
    const blob = new Blob([serializedCodes], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "musematic-mfa-backup-codes.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4 rounded-lg border border-border bg-background p-4">
      <div>
        <h3 className="text-sm font-semibold">{t("title")}</h3>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {codes.map((code) => (
          <code
            key={code}
            className="rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-sm"
          >
            {code}
          </code>
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={() => void copyCodes()}>
          {copied ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          ) : (
            <Copy className="h-4 w-4" />
          )}
          {copied ? t("copied") : t("copy")}
        </Button>
        <Button type="button" variant="outline" onClick={downloadCodes}>
          <Download className="h-4 w-4" />
          {t("download")}
        </Button>
      </div>
      <div className="flex items-start gap-3 rounded-md border border-border bg-muted/30 p-3">
        <Checkbox
          checked={acknowledged}
          id="mfa-backup-codes-saved"
          onChange={(event) => setAcknowledged(event.target.checked)}
        />
        <Label htmlFor="mfa-backup-codes-saved" className="leading-6">
          {t("acknowledge")}
        </Label>
      </div>
      <Button
        type="button"
        variant="secondary"
        disabled={!acknowledged}
        onClick={onDismiss}
      >
        <EyeOff className="h-4 w-4" />
        {t("dismiss")}
      </Button>
    </div>
  );
}
