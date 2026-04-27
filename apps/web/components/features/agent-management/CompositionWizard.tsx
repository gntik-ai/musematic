"use client";

import { useRouter } from "next/navigation";
import { Check, Sparkles } from "lucide-react";
import { WizardStepCustomize } from "@/components/features/agent-management/WizardStepCustomize";
import { WizardStepDescribe } from "@/components/features/agent-management/WizardStepDescribe";
import { WizardStepReviewBlueprint } from "@/components/features/agent-management/WizardStepReviewBlueprint";
import { WizardStepValidate } from "@/components/features/agent-management/WizardStepValidate";
import { WizardStepAttachBoth } from "@/components/features/agent-management/wizard/WizardStepAttachBoth";
import { WizardStepContextProfile } from "@/components/features/agent-management/wizard/WizardStepContextProfile";
import { WizardStepContract } from "@/components/features/agent-management/wizard/WizardStepContract";
import { WizardStepPreviewContract } from "@/components/features/agent-management/wizard/WizardStepPreviewContract";
import { WizardStepTestProfile } from "@/components/features/agent-management/wizard/WizardStepTestProfile";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { useCompositionWizardStore } from "@/lib/stores/use-composition-wizard-store";

const STEP_LABELS = [
  "Describe",
  "Review blueprint",
  "Customize",
  "Validate",
  "Context Profile",
  "Test Profile",
  "Contract",
  "Preview Contract",
  "Attach Both",
] as const;

type WizardStepNumber = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9;

export function CompositionWizard() {
  const router = useRouter();
  const blueprint = useCompositionWizardStore((state) => state.blueprint);
  const reset = useCompositionWizardStore((state) => state.reset);
  const setStep = useCompositionWizardStore((state) => state.setStep);
  const step = useCompositionWizardStore((state) => state.step);

  const handleNext = () => {
    if (step === 1 && !blueprint) {
      return;
    }

    if (step < STEP_LABELS.length) {
      setStep((step + 1) as WizardStepNumber);
    }
  };

  const handleBack = () => {
    if (step > 1) {
      setStep((step - 1) as WizardStepNumber);
    }
  };

  const handleCancel = () => {
    reset();
    router.push("/agent-management");
  };

  const content =
    step === 1 ? (
      <WizardStepDescribe />
    ) : blueprint ? (
      step === 2 ? (
        <WizardStepReviewBlueprint blueprint={blueprint} />
      ) : step === 3 ? (
        <WizardStepCustomize blueprint={blueprint} />
      ) : step === 4 ? (
        <WizardStepValidate blueprint={blueprint} />
      ) : step === 5 ? (
        <WizardStepContextProfile blueprint={blueprint} />
      ) : step === 6 ? (
        <WizardStepTestProfile blueprint={blueprint} />
      ) : step === 7 ? (
        <WizardStepContract blueprint={blueprint} />
      ) : step === 8 ? (
        <WizardStepPreviewContract blueprint={blueprint} />
      ) : (
        <WizardStepAttachBoth blueprint={blueprint} />
      )
    ) : (
      <EmptyState
        ctaLabel="Start over"
        description="Generate a blueprint first so the remaining wizard steps have content to work from."
        icon={Sparkles}
        title="Blueprint required"
        onCtaClick={() => setStep(1)}
      />
    );

  return (
    <section className="space-y-6">
      <div className="rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
              <Sparkles className="h-4 w-4" />
              Composition wizard
            </div>
            <h1 className="text-3xl font-semibold">Create an agent from intent</h1>
            <p className="max-w-3xl text-sm text-muted-foreground">
              Move from a natural-language brief to a validated draft agent in four guided steps.
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-9">
            {STEP_LABELS.map((label, index) => {
              const stepNumber = index + 1;
              const active = step === stepNumber;
              const complete = step > stepNumber;

              return (
                <div
                  key={label}
                  className={`rounded-2xl border px-4 py-3 text-sm ${
                    active
                      ? "border-brand-accent/40 bg-brand-accent/10 text-foreground"
                      : complete
                        ? "border-emerald-500/30 bg-emerald-500/10 text-foreground"
                        : "border-border/60 bg-background/70 text-muted-foreground"
                  }`}
                >
                  <div className="flex items-center gap-2 font-medium">
                    <span className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-current/20 text-xs">
                      {complete ? <Check className="h-3.5 w-3.5" /> : stepNumber}
                    </span>
                    {label}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {content}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button type="button" variant="ghost" onClick={handleCancel}>
          Cancel
        </Button>
        <div className="flex gap-3">
          <Button disabled={step === 1} type="button" variant="outline" onClick={handleBack}>
            Back
          </Button>
          {step < STEP_LABELS.length ? (
            <Button
              disabled={step === 1 && !blueprint}
              type="button"
              onClick={handleNext}
            >
              Next
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
