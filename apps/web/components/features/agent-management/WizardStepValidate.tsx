"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, LoaderCircle, XCircle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { buildDraftMetadataFromBlueprint } from "@/lib/agent-management/composition-wizard";
import { useCreateFromBlueprint, useValidateBlueprint } from "@/lib/hooks/use-composition";
import { useToast } from "@/lib/hooks/use-toast";
import { buildAgentManagementHref, type CompositionBlueprint } from "@/lib/types/agent-management";
import { useCompositionWizardStore } from "@/lib/stores/use-composition-wizard-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import { ApiError } from "@/types/api";

interface WizardStepValidateProps {
  blueprint: CompositionBlueprint;
}

export function WizardStepValidate({
  blueprint,
}: WizardStepValidateProps) {
  const router = useRouter();
  const createMutation = useCreateFromBlueprint();
  const validateBlueprintMutation = useValidateBlueprint();
  const { toast } = useToast();
  const workspace = useWorkspaceStore((state) => state.currentWorkspace);
  const customizations = useCompositionWizardStore((state) => state.customizations);
  const description = useCompositionWizardStore((state) => state.description);
  const setValidationResult = useCompositionWizardStore(
    (state) => state.setValidationResult,
  );
  const validationResult = useCompositionWizardStore(
    (state) => state.validation_result,
  );
  const validateBlueprint = validateBlueprintMutation.mutateAsync;
  const isValidationPending = validateBlueprintMutation.isPending;

  useEffect(() => {
    if (!workspace?.id) {
      setValidationResult(null);
      return;
    }

    let active = true;

    void validateBlueprint({
        blueprintId: blueprint.blueprint_id,
        workspace_id: workspace.id,
      })
      .then((result) => {
        if (active) {
          setValidationResult(result);
        }
      })
      .catch((error) => {
        if (!active) {
          return;
        }

        setValidationResult(null);
        toast({
          title: error instanceof ApiError ? error.message : "Blueprint validation failed",
          variant: "destructive",
        });
      });

    return () => {
      active = false;
    };
  }, [
    blueprint.blueprint_id,
    setValidationResult,
    toast,
    validateBlueprint,
    workspace?.id,
  ]);

  const handleCreateAgent = async () => {
    if (!workspace?.id) {
      toast({
        title: "Workspace required",
        description: "Select a workspace before creating a draft agent.",
        variant: "destructive",
      });
      return;
    }

    try {
      const metadata = buildDraftMetadataFromBlueprint({
        blueprint,
        customizations,
        description,
        workspaceSlug: workspace.slug,
      });
      const detail = await createMutation.mutateAsync({
        blueprint_id: blueprint.blueprint_id,
        workspace_id: workspace.id,
        metadata,
      });

      toast({
        title: "Draft agent created",
        variant: "success",
      });
      router.push(buildAgentManagementHref(detail.fqn));
    } catch (error) {
      toast({
        title: error instanceof ApiError ? error.message : "Unable to create the draft agent",
        variant: "destructive",
      });
    }
  };

  return (
    <div className="space-y-6 rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
      <div className="space-y-2">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
          Step 4
        </p>
        <h2 className="text-2xl font-semibold">Validate and create the draft</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          This step checks the composed draft against the frontend constraints before submitting it
          to the registry as a draft agent.
        </p>
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
                <p className="text-muted-foreground">{check.message}</p>
              </div>
            </div>
          ))}
        </div>
      ) : isValidationPending ? (
        <Alert>
          <AlertTitle>Validation in progress</AlertTitle>
          <AlertDescription>
            Running blueprint checks against the composition service.
          </AlertDescription>
        </Alert>
      ) : null}

      {!validationResult?.passed ? (
        <Alert variant="destructive">
          <AlertTitle>Validation has not passed yet</AlertTitle>
          <AlertDescription>
            Resolve the failing checks above before creating the draft agent.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex justify-end">
        <Button
          disabled={!validationResult?.passed || createMutation.isPending}
          type="button"
          onClick={() => void handleCreateAgent()}
        >
          {createMutation.isPending ? (
            <>
              <LoaderCircle className="h-4 w-4 animate-spin" />
              Creating agent…
            </>
          ) : (
            "Create agent"
          )}
        </Button>
      </div>
    </div>
  );
}
