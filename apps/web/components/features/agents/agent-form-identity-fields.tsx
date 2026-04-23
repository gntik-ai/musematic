"use client";

import type { UseFormReturn } from "react-hook-form";
import { z } from "zod";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useNamespaces } from "@/lib/hooks/use-namespaces";
import { cn } from "@/lib/utils";
import { useWorkspaceStore } from "@/store/workspace-store";

export const AGENT_FORM_ROLE_TYPES = [
  "researcher",
  "analyst",
  "reviewer",
  "operator",
  "verdict_authority",
  "tool_user",
  "integrator",
  "executor",
  "planner",
  "orchestrator",
  "observer",
  "judge",
  "enforcer",
  "custom",
] as const;

export type AgentFormRoleType = (typeof AGENT_FORM_ROLE_TYPES)[number];

export const AgentFormSchema = z.object({
  namespace: z.string().trim().min(1, "Namespace is required"),
  localName: z
    .string()
    .trim()
    .min(1, "Local name is required")
    .regex(/^[a-zA-Z0-9_-]+$/, "Use letters, numbers, underscores, or hyphens"),
  purpose: z
    .string()
    .trim()
    .min(50, "Purpose must be at least 50 characters"),
  approach: z.string().trim().max(5000).optional().default(""),
  roleType: z.enum(AGENT_FORM_ROLE_TYPES),
  visibilityPatterns: z.array(z.string().trim().min(1)).max(20).default([]),
});

export type AgentFormValues = z.infer<typeof AgentFormSchema>;

export const DEFAULT_AGENT_FORM_VALUES: AgentFormValues = {
  namespace: "",
  localName: "",
  purpose: "",
  approach: "",
  roleType: "operator",
  visibilityPatterns: [],
};

export interface AgentFormIdentityFieldsProps {
  form: UseFormReturn<AgentFormValues>;
  mode: "create" | "edit";
  isLegacy: boolean;
}

function toRoleLabel(value: AgentFormRoleType): string {
  return value
    .split(/[_-]/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function AgentFormIdentityFields({
  form,
  mode,
  isLegacy,
}: AgentFormIdentityFieldsProps) {
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const namespacesQuery = useNamespaces(workspaceId);
  const purpose = form.watch("purpose") ?? "";
  const purposeLength = purpose.trim().length;
  const errors = form.formState.errors;

  return (
    <div className="space-y-6">
      {isLegacy ? (
        <Alert>
          <AlertTitle>Legacy agent identity required</AlertTitle>
          <AlertDescription>
            This agent predates FQN identity. Assign a namespace and local name before saving so governance and discovery features can target it reliably.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
        <label className="space-y-2 text-sm">
          <span className="font-medium">Namespace</span>
          <Select
            aria-label="Namespace"
            value={form.watch("namespace")}
            onChange={(event) => {
              form.setValue("namespace", event.target.value, {
                shouldDirty: true,
                shouldValidate: true,
              });
            }}
          >
            <option value="">Select namespace</option>
            {(namespacesQuery.data ?? []).map((entry) => (
              <option key={entry.namespace} value={entry.namespace}>
                {entry.namespace}
              </option>
            ))}
          </Select>
          {errors.namespace?.message ? (
            <p className="text-xs text-destructive">{errors.namespace.message}</p>
          ) : null}
        </label>

        <label className="space-y-2 text-sm">
          <span className="font-medium">Local Name</span>
          <Input
            aria-label="Local Name"
            placeholder="kyc-verifier-v2"
            value={form.watch("localName")}
            onChange={(event) => {
              form.setValue("localName", event.target.value, {
                shouldDirty: true,
                shouldValidate: true,
              });
            }}
          />
          <p className="text-xs text-muted-foreground">
            {mode === "create"
              ? "Used to build the final FQN shown in catalog and governance flows."
              : "Changing this updates the displayed FQN everywhere the agent is referenced."}
          </p>
          {errors.localName?.message ? (
            <p className="text-xs text-destructive">{errors.localName.message}</p>
          ) : null}
        </label>
      </div>

      <label className="space-y-2 text-sm">
        <span className="font-medium">Purpose</span>
        <Textarea
          aria-label="Purpose"
          placeholder="Describe the operational objective, who it serves, and what success looks like."
          rows={5}
          value={form.watch("purpose")}
          onChange={(event) => {
            form.setValue("purpose", event.target.value, {
              shouldDirty: true,
              shouldValidate: true,
            });
          }}
        />
        <div className="flex items-center justify-between gap-3 text-xs">
          <p className="text-muted-foreground">
            Be explicit about scope, boundaries, and expected outcomes.
          </p>
          <span
            className={cn(
              "font-medium",
              purposeLength < 50 ? "text-destructive" : "text-muted-foreground",
            )}
          >
            {purposeLength} / 50
          </span>
        </div>
        {errors.purpose?.message ? (
          <p className="text-xs text-destructive">{errors.purpose.message}</p>
        ) : null}
      </label>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
        <label className="space-y-2 text-sm">
          <span className="font-medium">Approach</span>
          <Textarea
            aria-label="Approach"
            placeholder="Summarize how the agent reasons, what controls it applies, and when it escalates."
            rows={5}
            value={form.watch("approach")}
            onChange={(event) => {
              form.setValue("approach", event.target.value, {
                shouldDirty: true,
                shouldValidate: true,
              });
            }}
          />
          {errors.approach?.message ? (
            <p className="text-xs text-destructive">{errors.approach.message}</p>
          ) : null}
        </label>

        <label className="space-y-2 text-sm">
          <span className="font-medium">Role Type</span>
          <Select
            aria-label="Role Type"
            value={form.watch("roleType")}
            onChange={(event) => {
              form.setValue("roleType", event.target.value as AgentFormRoleType, {
                shouldDirty: true,
                shouldValidate: true,
              });
            }}
          >
            {AGENT_FORM_ROLE_TYPES.map((roleType) => (
              <option key={roleType} value={roleType}>
                {toRoleLabel(roleType)}
              </option>
            ))}
          </Select>
          <p className="text-xs text-muted-foreground">
            Role labels influence how this agent is grouped across governance, marketplace, and operator surfaces.
          </p>
          {errors.roleType?.message ? (
            <p className="text-xs text-destructive">{errors.roleType.message}</p>
          ) : null}
        </label>
      </div>
    </div>
  );
}
