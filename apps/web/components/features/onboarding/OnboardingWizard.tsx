"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, X } from "lucide-react";
import { OnboardingStepFirstAgent } from "@/components/features/onboarding/OnboardingStepFirstAgent";
import { OnboardingStepInvitations } from "@/components/features/onboarding/OnboardingStepInvitations";
import { OnboardingStepTour } from "@/components/features/onboarding/OnboardingStepTour";
import { OnboardingStepWorkspaceName } from "@/components/features/onboarding/OnboardingStepWorkspaceName";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { type OnboardingStep, useOnboarding } from "@/lib/hooks/use-onboarding";

export function OnboardingWizard() {
  const router = useRouter();
  const onboarding = useOnboarding();
  const state = onboarding.state.data;
  const [currentStep, setCurrentStep] = useState<OnboardingStep>("workspace_named");

  useEffect(() => {
    if (state) {
      setCurrentStep(firstRenderableStep(state.last_step_attempted, state.first_agent_step_available));
    }
  }, [state]);

  useEffect(() => {
    if (state?.last_step_attempted === "done" || state?.dismissed_at) {
      router.replace("/dashboard");
    }
  }, [router, state?.dismissed_at, state?.last_step_attempted]);

  const steps = useMemo(
    () => (state?.first_agent_step_available === false ? BASE_STEPS : FULL_STEPS),
    [state?.first_agent_step_available],
  );
  const stepIndex = Math.max(0, steps.indexOf(currentStep));
  const progress = ((stepIndex + 1) / steps.length) * 100;

  if (onboarding.state.isLoading || !state) {
    return (
      <div className="flex min-h-[360px] items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-brand-accent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <Progress value={progress} />
        </div>
        <Button
          aria-label="Dismiss onboarding"
          disabled={onboarding.dismiss.isPending}
          size="icon"
          type="button"
          variant="ghost"
          onClick={() => void onboarding.dismiss.mutateAsync(undefined)}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="rounded-md border border-border/70 bg-card p-5 shadow-sm sm:p-6">
        {currentStep === "workspace_named" ? (
          <OnboardingStepWorkspaceName
            defaultName={state.default_workspace_name ?? "My workspace"}
            isPending={onboarding.workspaceName.isPending}
            onSubmit={(workspaceName) =>
              void onboarding.workspaceName
                .mutateAsync({ workspace_name: workspaceName })
                .then(() => setCurrentStep("invitations"))
            }
          />
        ) : null}

        {currentStep === "invitations" ? (
          <OnboardingStepInvitations
            isPending={onboarding.invitations.isPending}
            onSubmit={(emails) =>
              void onboarding.invitations
                .mutateAsync({
                  invitations: emails.map((email) => ({ email, role: "workspace_member" })),
                })
                .then(() =>
                  setCurrentStep(state.first_agent_step_available ? "first_agent" : "tour"),
                )
            }
          />
        ) : null}

        {currentStep === "first_agent" ? (
          <OnboardingStepFirstAgent
            isPending={onboarding.firstAgent.isPending}
            onCreate={() =>
              void onboarding.firstAgent
                .mutateAsync({ skipped: false })
                .then(() => setCurrentStep("tour"))
            }
            onSkip={() =>
              void onboarding.firstAgent
                .mutateAsync({ skipped: true })
                .then(() => setCurrentStep("tour"))
            }
          />
        ) : null}

        {currentStep === "tour" ? (
          <OnboardingStepTour
            isPending={onboarding.tour.isPending}
            onFinish={() =>
              void onboarding.tour
                .mutateAsync({ skipped: false, started: true })
                .then(() => router.replace("/dashboard"))
            }
          />
        ) : null}
      </div>
    </div>
  );
}

const FULL_STEPS: OnboardingStep[] = ["workspace_named", "invitations", "first_agent", "tour"];
const BASE_STEPS: OnboardingStep[] = ["workspace_named", "invitations", "tour"];

function firstRenderableStep(step: OnboardingStep, firstAgentAvailable: boolean): OnboardingStep {
  if (step === "done") {
    return "tour";
  }
  if (step === "first_agent" && !firstAgentAvailable) {
    return "tour";
  }
  return step;
}
