"use client";

import { useMemo, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { MandatoryMfaStep } from "@/components/features/auth/MandatoryMfaStep";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import {
  type SetupStep,
  type TenantSetupValidationResponse,
  useTenantSetupMutations,
} from "@/lib/hooks/use-tenant-setup";

const STEPS: SetupStep[] = ["tos", "credentials", "mfa", "workspace", "invitations", "done"];
const TOS_VERSION = "2026-05-02";

interface TenantSetupWizardProps {
  initial: TenantSetupValidationResponse;
}

export function TenantSetupWizard({ initial }: TenantSetupWizardProps) {
  const [currentStep, setCurrentStep] = useState<SetupStep>(initial.current_step);
  const [tosAccepted, setTosAccepted] = useState(false);
  const [password, setPassword] = useState("");
  const [workspaceName, setWorkspaceName] = useState(defaultWorkspaceName(initial.target_email));
  const [invitationText, setInvitationText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const mutations = useTenantSetupMutations();
  const stepIndex = Math.max(0, STEPS.indexOf(currentStep));
  const progress = currentStep === "done" ? 100 : (stepIndex / (STEPS.length - 1)) * 100;

  const pending =
    mutations.complete.isPending ||
    mutations.credentials.isPending ||
    mutations.invitations.isPending ||
    mutations.tos.isPending ||
    mutations.workspace.isPending;

  const completed = useMemo(
    () => new Set([...initial.completed_steps, ...STEPS.slice(0, stepIndex)]),
    [initial.completed_steps, stepIndex],
  );

  async function runStep(action: () => Promise<{ next_step?: SetupStep }>, fallback: SetupStep) {
    setError(null);
    try {
      const response = await action();
      setCurrentStep(response.next_step ?? fallback);
    } catch (stepError) {
      setError(stepError instanceof Error ? stepError.message : "Unable to save this step.");
    }
  }

  async function completeSetup() {
    setError(null);
    try {
      const response = await mutations.complete.mutateAsync(undefined);
      window.location.assign(response.redirect_to || "/home");
    } catch (stepError) {
      setError(stepError instanceof Error ? stepError.message : "Unable to complete setup.");
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-brand-accent">
              Tenant setup
            </p>
            <h1 className="text-3xl font-semibold tracking-tight">Finish admin setup</h1>
          </div>
          <div className="rounded-md border border-border/70 px-3 py-2 text-sm text-muted-foreground">
            {initial.target_email}
          </div>
        </div>
        <Progress value={progress} />
        <div className="grid grid-cols-3 gap-2 text-xs text-muted-foreground sm:grid-cols-6">
          {STEPS.map((step) => (
            <span key={step} className="flex items-center gap-1">
              {completed.has(step) || step === "done" && currentStep === "done" ? (
                <Check className="h-3.5 w-3.5 text-emerald-500" />
              ) : null}
              {stepLabel(step)}
            </span>
          ))}
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {currentStep === "tos" ? (
        <div className="space-y-5">
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">Accept tenant terms</h2>
            <p className="text-sm text-muted-foreground">
              Admin access requires agreement to the current platform and AI disclosure terms.
            </p>
          </div>
          <div className="flex items-start gap-3 rounded-md border border-border/70 bg-card/70 p-4">
            <Checkbox
              checked={tosAccepted}
              id="tenant-setup-tos"
              onChange={(event) => setTosAccepted(event.currentTarget.checked)}
            />
            <Label className="leading-6" htmlFor="tenant-setup-tos">
              I accept the current tenant administrator terms
            </Label>
          </div>
          <Button
            className="w-full"
            disabled={!tosAccepted || mutations.tos.isPending}
            type="button"
            onClick={() =>
              void runStep(
                () =>
                  mutations.tos.mutateAsync({
                    accepted_at_ts: new Date().toISOString(),
                    tos_version: TOS_VERSION,
                  }),
                "credentials",
              )
            }
          >
            {mutations.tos.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Continue
          </Button>
        </div>
      ) : null}

      {currentStep === "credentials" ? (
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            void runStep(
              () => mutations.credentials.mutateAsync({ method: "password", password }),
              "mfa",
            );
          }}
        >
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">Create credentials</h2>
            <p className="text-sm text-muted-foreground">
              This password is scoped to this tenant identity.
            </p>
          </div>
          <Input
            autoComplete="new-password"
            minLength={12}
            placeholder="Create a tenant admin password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.currentTarget.value)}
          />
          <Button className="w-full" disabled={password.length < 12 || pending} type="submit">
            {mutations.credentials.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Save credentials
          </Button>
        </form>
      ) : null}

      {currentStep === "mfa" ? (
        <MandatoryMfaStep
          mutations={mutations}
          onComplete={() => {
            setCurrentStep("workspace");
          }}
        />
      ) : null}

      {currentStep === "workspace" ? (
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            void runStep(
              () => mutations.workspace.mutateAsync({ name: workspaceName }),
              "invitations",
            );
          }}
        >
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">Create the first workspace</h2>
            <p className="text-sm text-muted-foreground">
              The workspace owner is this tenant admin identity.
            </p>
          </div>
          <Input
            value={workspaceName}
            onChange={(event) => setWorkspaceName(event.currentTarget.value)}
          />
          <Button className="w-full" disabled={!workspaceName.trim() || pending} type="submit">
            {mutations.workspace.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Create workspace
          </Button>
        </form>
      ) : null}

      {currentStep === "invitations" ? (
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            void runStep(
              () =>
                mutations.invitations.mutateAsync({
                  invitations: parseInvitationEmails(invitationText),
                }),
              "done",
            );
          }}
        >
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">Invite teammates</h2>
            <p className="text-sm text-muted-foreground">
              Add one email per line, or continue without invitations.
            </p>
          </div>
          <Textarea
            placeholder={"alex@example.com\nsam@example.com"}
            value={invitationText}
            onChange={(event) => setInvitationText(event.currentTarget.value)}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <Button disabled={pending} type="submit">
              {mutations.invitations.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Send and continue
            </Button>
            <Button
              disabled={pending}
              type="button"
              variant="outline"
              onClick={() =>
                void runStep(
                  () => mutations.invitations.mutateAsync({ invitations: [] }),
                  "done",
                )
              }
            >
              Skip
            </Button>
          </div>
        </form>
      ) : null}

      {currentStep === "done" ? (
        <div className="space-y-5">
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold tracking-tight">Setup complete</h2>
            <p className="text-sm text-muted-foreground">
              Your tenant admin identity is ready.
            </p>
          </div>
          <Button className="w-full" disabled={mutations.complete.isPending} onClick={() => void completeSetup()}>
            {mutations.complete.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Enter tenant
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function defaultWorkspaceName(email: string): string {
  const localPart = email.split("@", 1)[0] || "Team";
  return `${localPart}'s workspace`;
}

function parseInvitationEmails(value: string) {
  return value
    .split(/[\n,]/)
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean)
    .map((email) => ({ email, role: "workspace_member" }));
}

function stepLabel(step: SetupStep): string {
  switch (step) {
    case "tos":
      return "Terms";
    case "credentials":
      return "Credentials";
    case "mfa":
      return "MFA";
    case "workspace":
      return "Workspace";
    case "invitations":
      return "Invites";
    case "done":
      return "Done";
  }
}
