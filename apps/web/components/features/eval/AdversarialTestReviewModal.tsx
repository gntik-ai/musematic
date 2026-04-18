"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogCancel,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useAteConfigs, useAteRun } from "@/lib/hooks/use-ate";
import { useEvalMutations } from "@/lib/hooks/use-eval-mutations";
import type { ATEGeneratedCase } from "@/types/evaluation";

export interface AdversarialTestReviewModalProps {
  open: boolean;
  workspaceId: string;
  evalSetId: string;
  agentFqn: string;
  onClose: () => void;
}

function parseGeneratedCases(report: Record<string, unknown> | null): ATEGeneratedCase[] {
  const rawItems = Array.isArray(report?.generated_cases)
    ? (report.generated_cases as Array<Record<string, unknown>>)
    : [];

  return rawItems.map((item, index) => ({
    id: `generated-${index}`,
    inputPrompt:
      typeof item.input_prompt === "string"
        ? item.input_prompt
        : typeof item.prompt === "string"
          ? item.prompt
          : "",
    expectedBehavior:
      typeof item.expected_behavior === "string"
        ? item.expected_behavior
        : typeof item.expected_output === "string"
          ? item.expected_output
          : "",
    category: typeof item.category === "string" ? item.category : "adversarial",
    accepted: null,
  }));
}

export function AdversarialTestReviewModal({
  open,
  workspaceId,
  evalSetId,
  agentFqn,
  onClose,
}: AdversarialTestReviewModalProps) {
  const { addCase, runAte } = useEvalMutations();
  const ateConfigsQuery = useAteConfigs(workspaceId);
  const [ateRunId, setAteRunId] = useState<string | null>(null);
  const ateRunQuery = useAteRun(ateRunId);
  const [generatedCases, setGeneratedCases] = useState<ATEGeneratedCase[]>([]);

  useEffect(() => {
    if (!open) {
      setAteRunId(null);
      setGeneratedCases([]);
    }
  }, [open]);

  useEffect(() => {
    if (ateRunQuery.data?.status !== "completed") {
      return;
    }
    setGeneratedCases(parseGeneratedCases(ateRunQuery.data.report));
  }, [ateRunQuery.data]);

  const defaultConfig = ateConfigsQuery.data?.items[0] ?? null;
  const acceptedCases = useMemo(
    () => generatedCases.filter((item) => item.accepted === true),
    [generatedCases],
  );

  const runGeneration = async () => {
    if (!defaultConfig || !agentFqn) {
      return;
    }

    const createdRun = await runAte.mutateAsync({
      ateConfigId: defaultConfig.id,
      agentFqn,
    });
    setAteRunId(createdRun.id);
  };

  const addAcceptedCases = async () => {
    for (const [index, item] of acceptedCases.entries()) {
      await addCase.mutateAsync({
        evalSetId,
        payload: {
          input_data: {
            prompt: item.editedInputPrompt ?? item.inputPrompt,
            input_prompt: item.editedInputPrompt ?? item.inputPrompt,
          },
          expected_output: item.editedExpectedOutput ?? item.expectedBehavior,
          category: item.category,
          position: index,
        },
      });
    }
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Adversarial test generation</DialogTitle>
          <DialogDescription>
            Generate adversarial prompts for {agentFqn || "the selected agent"} and review them before adding them to this suite.
          </DialogDescription>
        </DialogHeader>

        {ateConfigsQuery.data && ateConfigsQuery.data.items.length === 0 ? (
          <Alert>
            <AlertTitle>No ATE configuration found</AlertTitle>
            <AlertDescription>
              An admin must set up adversarial testing before operators can generate cases.
            </AlertDescription>
          </Alert>
        ) : null}

        {ateRunQuery.data?.status === "pre_check_failed" ? (
          <Alert variant="destructive">
            <AlertTitle>Pre-check failed</AlertTitle>
            <AlertDescription>
              {(ateRunQuery.data.pre_check_errors ?? []).map((error, index) => (
                <span className="block" key={index}>
                  {String(error)}
                </span>
              ))}
            </AlertDescription>
          </Alert>
        ) : null}

        {ateRunQuery.isLoading || ateRunQuery.data?.status === "pending" || ateRunQuery.data?.status === "running" ? (
          <div className="rounded-2xl border border-border/70 bg-card/70 p-6 text-sm text-muted-foreground">
            Generating adversarial cases…
          </div>
        ) : null}

        {generatedCases.length > 0 ? (
          <div className="space-y-4">
            {generatedCases.map((item) => (
              <div
                className="space-y-3 rounded-2xl border border-border/70 bg-card/70 p-4"
                key={item.id}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{item.category}</Badge>
                  <Badge
                    variant={
                      item.accepted === true
                        ? "secondary"
                        : item.accepted === false
                          ? "destructive"
                          : "outline"
                    }
                  >
                    {item.accepted === true
                      ? "Accepted"
                      : item.accepted === false
                        ? "Edited"
                        : "Pending review"}
                  </Badge>
                </div>
                <Input
                  value={item.editedInputPrompt ?? item.inputPrompt}
                  onChange={(event) =>
                    setGeneratedCases((current) =>
                      current.map((entry) =>
                        entry.id === item.id
                          ? { ...entry, editedInputPrompt: event.target.value, accepted: false }
                          : entry,
                      ),
                    )
                  }
                />
                <Textarea
                  value={item.editedExpectedOutput ?? item.expectedBehavior}
                  onChange={(event) =>
                    setGeneratedCases((current) =>
                      current.map((entry) =>
                        entry.id === item.id
                          ? {
                              ...entry,
                              editedExpectedOutput: event.target.value,
                              accepted: false,
                            }
                          : entry,
                      ),
                    )
                  }
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={() =>
                      setGeneratedCases((current) =>
                        current.map((entry) =>
                          entry.id === item.id ? { ...entry, accepted: true } : entry,
                        ),
                      )
                    }
                    variant="secondary"
                  >
                    Accept
                  </Button>
                  <Button
                    onClick={() =>
                      setGeneratedCases((current) =>
                        current.filter((entry) => entry.id !== item.id),
                      )
                    }
                    variant="outline"
                  >
                    Discard
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : null}

        <DialogFooter>
          <DialogCancel className="rounded-md border border-border px-4 py-2 text-sm">
            Close
          </DialogCancel>
          <Button
            disabled={!defaultConfig || !agentFqn || runAte.isPending}
            variant="outline"
            onClick={runGeneration}
          >
            Generate
          </Button>
          <Button
            disabled={acceptedCases.length === 0 || addCase.isPending}
            onClick={addAcceptedCases}
          >
            Add Accepted Cases
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
