"use client";

import { useState } from "react";
import { Play } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useContractPreview } from "@/lib/hooks/use-contract-preview";
import { RealLLMOptInDialog } from "./RealLLMOptInDialog";

export function ContractPreviewPanel({ contractId }: { contractId?: string | null }) {
  const [sampleInput, setSampleInput] = useState('{"output":{"answer":"ok"},"tokens":120}');
  const [inputError, setInputError] = useState<string | null>(null);
  const preview = useContractPreview(contractId);

  function runPreview(useMock = true, costAcknowledged = false) {
    setInputError(null);
    let parsed: Record<string, unknown>;

    try {
      const value = JSON.parse(sampleInput) as unknown;
      if (typeof value !== "object" || value === null || Array.isArray(value)) {
        throw new Error("Sample input must be a JSON object.");
      }
      parsed = value as Record<string, unknown>;
    } catch (error) {
      setInputError(error instanceof Error ? error.message : "Sample input is invalid JSON.");
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
          Run Mock Preview
        </Button>
        <RealLLMOptInDialog disabled={!contractId} onConfirm={() => runPreview(false, true)} />
      </div>
      {inputError || preview.error ? (
        <Alert variant="destructive">
          <AlertDescription>
            {inputError ?? preview.error?.message ?? "Unable to preview contract."}
          </AlertDescription>
        </Alert>
      ) : null}
      {preview.data ? (
        <div className="space-y-3 rounded-lg border p-4">
          <div className="flex flex-wrap gap-2">
            <Badge>{preview.data.final_action}</Badge>
            {preview.data.was_fallback ? <Badge variant="outline">Fallback</Badge> : null}
          </div>
          <p className="text-sm text-muted-foreground">{preview.data.mock_response}</p>
          <div className="grid gap-3 md:grid-cols-3">
            <ClauseList label="Triggered" values={preview.data.clauses_triggered} />
            <ClauseList label="Satisfied" values={preview.data.clauses_satisfied} />
            <ClauseList label="Violated" values={preview.data.clauses_violated} />
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
