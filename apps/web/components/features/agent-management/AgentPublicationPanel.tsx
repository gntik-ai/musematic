"use client";

import { useMemo, useState } from "react";
import { CheckCircle2, ShieldAlert, XCircle } from "lucide-react";
import { PublicationConfirmDialog } from "@/components/features/agent-management/PublicationConfirmDialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { usePublishAgent, useValidateAgent } from "@/lib/hooks/use-agent-mutations";
import { useToast } from "@/lib/hooks/use-toast";
import type {
  AgentStatus,
  PublicationSummary,
  ValidationResult,
} from "@/lib/types/agent-management";
import { ApiError } from "@/types/api";

export interface AgentPublicationPanelProps {
  fqn: string;
  currentStatus: AgentStatus;
  onPublished: () => void;
}

function buildPublicationPreview(
  fqn: string,
  currentStatus: AgentStatus,
): PublicationSummary {
  return {
    fqn,
    previous_status: currentStatus,
    new_status: "active",
    affected_workspaces: ["Current workspace"],
    published_at: new Date().toISOString(),
  };
}

export function AgentPublicationPanel({
  fqn,
  currentStatus,
  onPublished,
}: AgentPublicationPanelProps) {
  const validateMutation = useValidateAgent();
  const publishMutation = usePublishAgent();
  const { toast } = useToast();
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const publicationPreview = useMemo(
    () => buildPublicationPreview(fqn, currentStatus),
    [currentStatus, fqn],
  );

  return (
    <div className="space-y-4 rounded-2xl border border-border/60 bg-card/80 p-5">
      <div>
        <h3 className="text-lg font-semibold">Publication workflow</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Validate the draft before promoting it to active.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Button
          disabled={validateMutation.isPending}
          type="button"
          variant="outline"
          onClick={async () => {
            try {
              const result = await validateMutation.mutateAsync(fqn);
              setValidationResult(result);
            } catch (error) {
              toast({
                title: error instanceof ApiError ? error.message : "Validation failed",
                variant: "destructive",
              });
            }
          }}
        >
          {validateMutation.isPending ? "Validating…" : "Validate"}
        </Button>
        <Button
          disabled={!validationResult?.passed || publishMutation.isPending}
          type="button"
          onClick={() => setConfirmOpen(true)}
        >
          Publish
        </Button>
      </div>

      {validationResult ? (
        <div className="space-y-3">
          {validationResult.checks.map((check) => (
            <div
              key={check.name}
              className="flex items-start gap-3 rounded-xl border border-border/60 bg-background/70 px-4 py-3 text-sm"
            >
              {check.passed ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-500" />
              ) : (
                <XCircle className="mt-0.5 h-4 w-4 text-rose-500" />
              )}
              <div>
                <p className="font-medium">{check.name}</p>
                <p className="text-muted-foreground">
                  {check.message ?? (check.passed ? "Passed" : "Failed")}
                </p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Alert>
          <ShieldAlert className="h-4 w-4" />
          <AlertTitle>No validation run yet</AlertTitle>
          <AlertDescription>
            Run validation to inspect publish readiness before activating the agent.
          </AlertDescription>
        </Alert>
      )}

      <PublicationConfirmDialog
        open={confirmOpen}
        summary={publicationPreview}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={async () => {
          try {
            await publishMutation.mutateAsync(fqn);
            setConfirmOpen(false);
            toast({
              title: "Agent published",
              variant: "success",
            });
            onPublished();
          } catch (error) {
            setConfirmOpen(false);
            toast({
              title: error instanceof ApiError ? error.message : "Publish failed",
              variant: "destructive",
            });
          }
        }}
      />
    </div>
  );
}
