"use client";

import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useWorkspaces } from "@/lib/hooks/use-workspaces";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { InvocationSchema, type InvocationValues } from "@/lib/schemas/marketplace";
import { useWorkspaceStore } from "@/store/workspace-store";

export interface InvokeAgentDialogProps {
  agentFqn: string;
  agentDisplayName: string;
  isVisible: boolean;
  trigger: React.ReactNode;
}

type Step = "workspace" | "brief";

export function InvokeAgentDialog({
  agentFqn,
  agentDisplayName,
  isVisible,
  trigger,
}: InvokeAgentDialogProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>("workspace");
  const currentWorkspace = useWorkspaceStore((state) => state.currentWorkspace);
  const { isLoading, isError, workspaces } = useWorkspaces({
    enabled: open && isVisible,
  });
  const form = useForm<InvocationValues>({
    resolver: zodResolver(InvocationSchema),
    defaultValues: {
      workspaceId: currentWorkspace?.id ?? "",
      taskBrief: "",
    },
  });

  useEffect(() => {
    if (!open) {
      setStep("workspace");
      form.reset({
        workspaceId: currentWorkspace?.id ?? "",
        taskBrief: "",
      });
      return;
    }

    if (workspaces.length === 1) {
      form.setValue("workspaceId", workspaces[0]?.id ?? "");
      setStep("brief");
    }
  }, [currentWorkspace?.id, form, open, workspaces]);

  const workspaceId = form.watch("workspaceId");
  const selectedWorkspace =
    workspaces.find((workspace) => workspace.id === workspaceId) ?? null;

  const handleSubmit = form.handleSubmit((values) => {
    if (!isVisible) {
      return;
    }

    const nextParams = new URLSearchParams();
    nextParams.set("agent", agentFqn);
    nextParams.set("workspace", values.workspaceId);
    if (values.taskBrief) {
      nextParams.set("brief", values.taskBrief);
    }

    setOpen(false);
    router.push(`/conversations/new?${nextParams.toString()}`);
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Start conversation</DialogTitle>
          <DialogDescription>
            Launch {agentDisplayName} in a workspace and seed the conversation with a task brief.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form className="space-y-5" onSubmit={handleSubmit}>
            {step === "workspace" ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <p className="text-sm font-medium">Choose a workspace</p>
                  <p className="text-sm text-muted-foreground">
                    The new conversation will inherit that workspace&apos;s policies, memory, and connectors.
                  </p>
                </div>

                {isLoading ? (
                  <div className="rounded-2xl border border-border/60 p-4 text-sm text-muted-foreground">
                    Loading workspaces…
                  </div>
                ) : null}

                {isError ? (
                  <div className="rounded-2xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
                    Workspaces could not be loaded right now.
                  </div>
                ) : null}

                {workspaces.length > 1 ? (
                  <FormField
                    control={form.control}
                    name="workspaceId"
                    render={({ field }) => (
                      <FormItem className="space-y-3">
                        <FormControl>
                          <div className="space-y-3" role="radiogroup">
                            {workspaces.map((workspace) => {
                              const checked = field.value === workspace.id;
                              return (
                                <label
                                  key={workspace.id}
                                  className="flex cursor-pointer items-start gap-3 rounded-2xl border border-border/60 bg-card/70 p-4 transition hover:border-brand-accent/40"
                                >
                                  <input
                                    aria-label={workspace.name}
                                    checked={checked}
                                    className="mt-1 h-4 w-4 accent-[hsl(var(--primary))]"
                                    name="workspaceId"
                                    type="radio"
                                    value={workspace.id}
                                    onChange={() => field.onChange(workspace.id)}
                                  />
                                  <div>
                                    <p className="font-medium">{workspace.name}</p>
                                    <p className="text-sm text-muted-foreground">
                                      {workspace.description ?? "No description"}
                                    </p>
                                  </div>
                                </label>
                              );
                            })}
                          </div>
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                ) : null}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="rounded-2xl border border-border/60 bg-muted/30 p-4">
                  <p className="text-sm font-medium">Selected workspace</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {selectedWorkspace?.name ?? currentWorkspace?.name ?? "Current workspace"}
                  </p>
                </div>
                <FormField
                  control={form.control}
                  name="taskBrief"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Task brief</FormLabel>
                      <FormControl>
                        <Textarea
                          maxLength={500}
                          placeholder="Describe the outcome you want from this conversation."
                          {...field}
                          value={field.value ?? ""}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            )}

            <DialogFooter className="justify-between">
              {step === "brief" && workspaces.length > 1 ? (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setStep("workspace")}
                >
                  Back
                </Button>
              ) : (
                <div />
              )}
              {step === "workspace" ? (
                <Button
                  disabled={isLoading || !workspaceId}
                  type="button"
                  onClick={() => setStep("brief")}
                >
                  Next
                </Button>
              ) : (
                <Button disabled={!workspaceId} type="submit">
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Loading
                    </>
                  ) : (
                    "Start Conversation"
                  )}
                </Button>
              )}
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
