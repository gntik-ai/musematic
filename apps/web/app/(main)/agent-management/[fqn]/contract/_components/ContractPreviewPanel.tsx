"use client";

import { useState } from "react";
import { Play } from "lucide-react";
import { useTranslations } from "next-intl";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { RealLLMOptInDialog } from "@/components/features/shared/RealLLMOptInDialog";
import { useContractPreview } from "@/lib/hooks/use-contract-preview";

export function ContractPreviewPanel({ contractId }: { contractId?: string | null }) {
  const t = useTranslations("creator.contract");
  const [sampleInput, setSampleInput] = useState('{"output":{"answer":"ok"},"tokens":120}');
  const [inputError, setInputError] = useState<string | null>(null);
  const preview = useContractPreview(contractId);

  function runPreview(useMock = true, costAcknowledged = false) {
    setInputError(null);
    let parsed: Record<string, unknown>;

    try {
      const value = JSON.parse(sampleInput) as unknown;
      if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new Error(t("sampleInputObjectRequired"));
      }
      parsed = value as Record<string, unknown>;
    } catch (error) {
      setInputError(error instanceof Error ? error.message : t("sampleInputInvalid"));
      return;
    }

    preview.mutate({
      sampleInput: parsed,
      useMock,
      costAcknowledged,
    });
  }

  return (
    <div className="space-y-4">
      <Textarea value={sampleInput} onChange={(event) => setSampleInput(event.target.value)} />
      <div className="flex flex-wrap gap-2">
        <Button disabled={!contractId || preview.isPending} type="button" onClick={() => runPreview()}>
          <Play className="h-4 w-4" />
          {t("runMockPreview")}
        </Button>
        <RealLLMOptInDialog disabled={!contractId} onConfirm={() => runPreview(false, true)} />
      </div>
      {inputError || preview.error ? (
        <Alert variant="destructive">
          <AlertDescription>
            {inputError ?? preview.error?.message ?? t("previewFailure")}
          </AlertDescription>
        </Alert>
      ) : null}
      {preview.data ? (
        <div className="space-y-3 rounded-lg border p-4">
          <div className="flex flex-wrap gap-2">
            <Badge>{preview.data.final_action}</Badge>
            {preview.data.was_fallback ? <Badge variant="outline">{t("fallback")}</Badge> : null}
          </div>
          <p className="text-sm text-muted-foreground">{preview.data.mock_response}</p>
          <div className="grid gap-3 md:grid-cols-3">
            <ClauseList label={t("triggered")} values={preview.data.clauses_triggered} />
            <ClauseList label={t("satisfied")} values={preview.data.clauses_satisfied} />
            <ClauseList label={t("violated")} values={preview.data.clauses_violated} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ClauseList({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <p className="text-sm font-medium">{label}</p>
      <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </div>
  );
}
