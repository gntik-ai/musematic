"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Pause, Play, SkipForward, Square, RotateCcw, FlaskConical } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/lib/hooks/use-toast";
import {
  useCancelExecution,
  useInjectVariable,
  usePauseExecution,
  useResumeExecution,
  useRetryStep,
  useSkipStep,
} from "@/lib/hooks/use-execution-controls";
import { useExecutionMonitorStore } from "@/lib/stores/execution-monitor-store";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/auth-store";

const injectVariableSchema = z.object({
  variableName: z.string().min(1, "Variable name is required."),
  value: z
    .string()
    .min(1, "Value is required.")
    .superRefine((value, context) => {
      try {
        JSON.parse(value);
      } catch {
        context.addIssue({
          code: "custom",
          message: "Value must be valid JSON.",
        });
      }
    }),
  reason: z.string().optional(),
});

type InjectVariableFormValues = z.infer<typeof injectVariableSchema>;
type ControlAction = "pause" | "resume" | "cancel" | "retry" | "skip";

const operatorRoles = new Set([
  "superadmin",
  "workspace_admin",
  "workspace_editor",
  "agent_operator",
  "operator",
]);

function getActionCopy(action: ControlAction, stepId: string | null) {
  switch (action) {
    case "pause":
      return {
        title: "Pause execution",
        description:
          "The current execution will stop dispatching new work until it is resumed.",
        confirmLabel: "Pause execution",
        variant: "default" as const,
      };
    case "resume":
      return {
        title: "Resume execution",
        description:
          "The execution will continue from its paused state and resume pending work.",
        confirmLabel: "Resume execution",
        variant: "default" as const,
      };
    case "cancel":
      return {
        title: "Cancel execution",
        description:
          "This execution will be canceled and any remaining steps will stop running.",
        confirmLabel: "Cancel execution",
        variant: "destructive" as const,
      };
    case "retry":
      return {
        title: "Retry failed step",
        description: `Step ${stepId ?? "selected step"} will be re-queued for execution.`,
        confirmLabel: "Retry step",
        variant: "default" as const,
      };
    case "skip":
      return {
        title: "Skip selected step",
        description:
          `Step ${stepId ?? "selected step"} will be marked as skipped so the workflow can continue.`,
        confirmLabel: "Skip step",
        variant: "default" as const,
      };
    default:
      return {
        title: "Confirm action",
        description: "Confirm the requested execution action.",
        confirmLabel: "Continue",
        variant: "default" as const,
      };
  }
}

function ControlButton({
  disabled,
  icon: Icon,
  label,
  onClick,
  title,
}: {
  disabled: boolean;
  icon: typeof Pause;
  label: string;
  onClick: () => void;
  title: string | undefined;
}) {
  return (
    <Button
      className={cn("justify-start sm:justify-center")}
      disabled={disabled}
      onClick={onClick}
      title={title}
      variant="outline"
    >
      <Icon className="h-4 w-4" />
      {label}
    </Button>
  );
}

export function ExecutionControls({
  executionId,
  selectedStepId: selectedStepIdProp,
}: {
  executionId: string;
  selectedStepId?: string | null;
}) {
  const executionStatus = useExecutionMonitorStore((state) => state.executionStatus);
  const storeSelectedStepId = useExecutionMonitorStore((state) => state.selectedStepId);
  const stepStatuses = useExecutionMonitorStore((state) => state.stepStatuses);
  const selectedStepId = selectedStepIdProp ?? storeSelectedStepId;
  const [pendingAction, setPendingAction] = useState<ControlAction | null>(null);
  const [injectDialogOpen, setInjectDialogOpen] = useState(false);
  const userRoles = useAuthStore((state) => state.user?.roles ?? []);

  const pauseExecution = usePauseExecution(executionId);
  const resumeExecution = useResumeExecution(executionId);
  const cancelExecution = useCancelExecution(executionId);
  const retryStep = useRetryStep(executionId);
  const skipStep = useSkipStep(executionId);
  const injectVariable = useInjectVariable(executionId);

  const form = useForm<InjectVariableFormValues>({
    defaultValues: {
      variableName: "",
      value: "",
      reason: "",
    },
    resolver: zodResolver(injectVariableSchema),
  });

  const hasOperatorAccess = useMemo(
    () => userRoles.some((role) => operatorRoles.has(role)),
    [userRoles],
  );
  const selectedStepStatus = selectedStepId ? stepStatuses[selectedStepId] : null;
  const disabledReason = hasOperatorAccess
    ? undefined
    : "You do not have permission to control executions.";

  const actionCopy = pendingAction
    ? getActionCopy(pendingAction, selectedStepId)
    : null;
  const isConfirming =
    pauseExecution.isPending ||
    resumeExecution.isPending ||
    cancelExecution.isPending ||
    retryStep.isPending ||
    skipStep.isPending;

  const handleActionError = (error: unknown) => {
    toast({
      title: "Execution action failed",
      description:
        error instanceof Error ? error.message : "The action could not be completed.",
      variant: "destructive",
    });
  };

  const executePendingAction = async () => {
    if (!pendingAction) {
      return;
    }

    try {
      if (pendingAction === "pause") {
        await pauseExecution.mutateAsync(undefined);
      }
      if (pendingAction === "resume") {
        await resumeExecution.mutateAsync(undefined);
      }
      if (pendingAction === "cancel") {
        await cancelExecution.mutateAsync({});
      }
      if (pendingAction === "retry" && selectedStepId) {
        await retryStep.mutateAsync({ stepId: selectedStepId });
      }
      if (pendingAction === "skip" && selectedStepId) {
        await skipStep.mutateAsync({ stepId: selectedStepId });
      }

      setPendingAction(null);
    } catch (error) {
      handleActionError(error);
    }
  };

  return (
    <>
      <div className="flex flex-wrap gap-3">
        <ControlButton
          disabled={!hasOperatorAccess || executionStatus !== "running"}
          icon={Pause}
          label="Pause"
          onClick={() => setPendingAction("pause")}
          title={
            disabledReason ??
            (executionStatus !== "running"
              ? "Execution must be running to pause."
              : undefined)
          }
        />
        <ControlButton
          disabled={!hasOperatorAccess || executionStatus !== "paused"}
          icon={Play}
          label="Resume"
          onClick={() => setPendingAction("resume")}
          title={
            disabledReason ??
            (executionStatus !== "paused"
              ? "Execution must be paused to resume."
              : undefined)
          }
        />
        <ControlButton
          disabled={
            !hasOperatorAccess ||
            (executionStatus !== "running" && executionStatus !== "paused")
          }
          icon={Square}
          label="Cancel"
          onClick={() => setPendingAction("cancel")}
          title={
            disabledReason ??
            (executionStatus !== "running" && executionStatus !== "paused"
              ? "Execution must be running or paused to cancel."
              : undefined)
          }
        />
        <ControlButton
          disabled={!hasOperatorAccess || selectedStepStatus !== "failed"}
          icon={RotateCcw}
          label="Retry"
          onClick={() => setPendingAction("retry")}
          title={
            disabledReason ??
            (selectedStepStatus !== "failed"
              ? "Select a failed step to retry it."
              : undefined)
          }
        />
        <ControlButton
          disabled={!hasOperatorAccess || selectedStepStatus !== "pending"}
          icon={SkipForward}
          label="Skip"
          onClick={() => setPendingAction("skip")}
          title={
            disabledReason ??
            (selectedStepStatus !== "pending"
              ? "Select a pending step to skip it."
              : undefined)
          }
        />
        <ControlButton
          disabled={
            !hasOperatorAccess ||
            (executionStatus !== "running" && executionStatus !== "paused")
          }
          icon={FlaskConical}
          label="Inject Variable"
          onClick={() => setInjectDialogOpen(true)}
          title={
            disabledReason ??
            (executionStatus !== "running" && executionStatus !== "paused"
              ? "Execution must be running or paused to inject a variable."
              : undefined)
          }
        />
      </div>

      <ConfirmDialog
        confirmLabel={actionCopy?.confirmLabel ?? "Confirm"}
        description={actionCopy?.description ?? ""}
        isLoading={isConfirming}
        onConfirm={() => {
          void executePendingAction();
        }}
        onOpenChange={(open) => {
          if (!open) {
            setPendingAction(null);
          }
        }}
        open={pendingAction !== null}
        title={actionCopy?.title ?? ""}
        variant={actionCopy?.variant ?? "default"}
      />

      <Dialog
        onOpenChange={(open) => {
          setInjectDialogOpen(open);
          if (!open) {
            form.reset();
          }
        }}
        open={injectDialogOpen}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Inject variable</DialogTitle>
            <DialogDescription>
              Apply a temporary runtime override to the current execution.
            </DialogDescription>
          </DialogHeader>

          <Form {...form}>
            <form
              className="space-y-4"
              onSubmit={form.handleSubmit(async (values) => {
                try {
                  await injectVariable.mutateAsync({
                    variableName: values.variableName,
                    value: JSON.parse(values.value),
                    reason: values.reason || undefined,
                  });
                  toast({
                    title: "Variable injected",
                    description: `${values.variableName} was applied to the execution.`,
                    variant: "success",
                  });
                  setInjectDialogOpen(false);
                  form.reset();
                } catch (error) {
                  handleActionError(error);
                }
              })}
            >
              <FormField
                control={form.control}
                name="variableName"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Variable name</FormLabel>
                    <FormControl>
                      <Input placeholder="risk_threshold" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="value"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Value</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder='{"threshold": 0.9}'
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="reason"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Reason</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Optional note for the audit trail"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button
                  onClick={() => {
                    setInjectDialogOpen(false);
                    form.reset();
                  }}
                  type="button"
                  variant="outline"
                >
                  Cancel
                </Button>
                <Button disabled={injectVariable.isPending} type="submit">
                  {injectVariable.isPending ? "Injecting..." : "Inject variable"}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </>
  );
}
