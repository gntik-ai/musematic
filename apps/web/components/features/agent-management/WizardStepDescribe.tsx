"use client";

import Link from "next/link";
import { LoaderCircle, Sparkles } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useGenerateBlueprint } from "@/lib/hooks/use-composition";
import { useToast } from "@/lib/hooks/use-toast";
import { useCompositionWizardStore } from "@/lib/stores/use-composition-wizard-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import { ApiError } from "@/types/api";

export function WizardStepDescribe() {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const generateBlueprint = useGenerateBlueprint();
  const { toast } = useToast();
  const description = useCompositionWizardStore((state) => state.description);
  const error = useCompositionWizardStore((state) => state.error);
  const setBlueprint = useCompositionWizardStore((state) => state.setBlueprint);
  const setDescription = useCompositionWizardStore((state) => state.setDescription);
  const setError = useCompositionWizardStore((state) => state.setError);
  const setLoading = useCompositionWizardStore((state) => state.setLoading);
  const setStep = useCompositionWizardStore((state) => state.setStep);
  const setValidationResult = useCompositionWizardStore(
    (state) => state.setValidationResult,
  );

  const handleGenerate = async () => {
    if (!workspaceId) {
      setError("Select a workspace before generating a blueprint.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const blueprint = await generateBlueprint.mutateAsync({
        description,
        workspace_id: workspaceId,
      });
      setBlueprint(blueprint);
      setValidationResult(null);
      setStep(2);
    } catch (errorValue) {
      const nextError =
        errorValue instanceof ApiError && errorValue.status === 503
          ? "Composition service unavailable. Retry or use the manual upload path."
          : errorValue instanceof ApiError
            ? errorValue.message
            : "Unable to generate a blueprint right now.";
      setError(nextError);
      toast({
        title: "Blueprint generation failed",
        description: nextError,
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
          <Sparkles className="h-4 w-4" />
          Step 1
        </div>
        <h2 className="text-2xl font-semibold">Describe the agent you want to create</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Explain the agent&apos;s responsibility, the data it should work with, and any tools or
          policies you already expect it to need.
        </p>
      </div>

      <label className="space-y-2 text-sm">
        <span className="font-medium">Natural-language description</span>
        <Textarea
          aria-label="Agent description"
          className="min-h-40"
          placeholder="An agent that monitors financial transactions for fraud, escalates suspicious activity, and keeps a traceable audit trail."
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>

      {error ? (
        <Alert
          className="border-amber-500/30 bg-amber-500/10"
          role="status"
        >
          <AlertTitle>Blueprint generation needs attention</AlertTitle>
          <AlertDescription>
            {error}
          </AlertDescription>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button
              disabled={generateBlueprint.isPending}
              type="button"
              variant="outline"
              onClick={() => void handleGenerate()}
            >
              Retry
            </Button>
            <Button asChild type="button" variant="secondary">
              <Link href="/agent-management">Go to manual upload</Link>
            </Button>
          </div>
        </Alert>
      ) : null}

      <div className="flex justify-end">
        <Button
          disabled={description.trim().length < 10 || generateBlueprint.isPending}
          type="button"
          onClick={() => void handleGenerate()}
        >
          {generateBlueprint.isPending ? (
            <>
              <LoaderCircle className="h-4 w-4 animate-spin" />
              Generating blueprint…
            </>
          ) : (
            "Generate blueprint"
          )}
        </Button>
      </div>
    </div>
  );
}
