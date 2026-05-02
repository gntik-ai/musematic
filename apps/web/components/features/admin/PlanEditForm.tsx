"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2, Save } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { PlanVersionDiff } from "@/components/features/admin/PlanVersionDiff";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useAdminPlan,
  useCreatePlan,
  usePublishPlanVersion,
  useUpdatePlanMetadata,
  type AdminPlan,
  type PlanVersion,
  type PlanVersionPublishPayload,
} from "@/lib/hooks/use-admin-plans";
import { toast } from "@/lib/hooks/use-toast";

const planFormSchema = z.object({
  slug: z.string().min(1).max(32),
  display_name: z.string().min(1).max(128),
  description: z.string().optional(),
  tier: z.enum(["free", "pro", "enterprise"]),
  is_public: z.preprocess((value) => value === true || value === "true", z.boolean()),
  is_active: z.preprocess((value) => value === true || value === "true", z.boolean()),
  allowed_model_tier: z.enum(["cheap_only", "standard", "all"]),
  price_monthly: z.coerce.number().min(0),
  executions_per_day: z.coerce.number().int().min(0),
  executions_per_month: z.coerce.number().int().min(0),
  minutes_per_day: z.coerce.number().int().min(0),
  minutes_per_month: z.coerce.number().int().min(0),
  max_workspaces: z.coerce.number().int().min(0),
  max_agents_per_workspace: z.coerce.number().int().min(0),
  max_users_per_workspace: z.coerce.number().int().min(0),
  overage_price_per_minute: z.coerce.number().min(0),
  trial_days: z.coerce.number().int().min(0),
  quota_period_anchor: z.enum(["calendar_month", "subscription_anniversary"]),
});

type PlanFormValues = z.infer<typeof planFormSchema>;

interface PlanEditFormProps {
  slug?: string;
  mode?: "create" | "edit";
  onFinished?: () => void;
}

const DEFAULT_VALUES: PlanFormValues = {
  slug: "",
  display_name: "",
  description: "",
  tier: "pro",
  is_public: true,
  is_active: true,
  allowed_model_tier: "all",
  price_monthly: 0,
  executions_per_day: 0,
  executions_per_month: 0,
  minutes_per_day: 0,
  minutes_per_month: 0,
  max_workspaces: 0,
  max_agents_per_workspace: 0,
  max_users_per_workspace: 0,
  overage_price_per_minute: 0,
  trial_days: 0,
  quota_period_anchor: "calendar_month",
};

function valuesFromPlan(plan?: AdminPlan | null): PlanFormValues {
  if (!plan) {
    return DEFAULT_VALUES;
  }
  const version = plan.current_version;
  return {
    slug: plan.slug,
    display_name: plan.display_name,
    description: plan.description ?? "",
    tier: plan.tier,
    is_public: plan.is_public,
    is_active: plan.is_active,
    allowed_model_tier: plan.allowed_model_tier,
    price_monthly: Number(version?.price_monthly ?? 0),
    executions_per_day: version?.executions_per_day ?? 0,
    executions_per_month: version?.executions_per_month ?? 0,
    minutes_per_day: version?.minutes_per_day ?? 0,
    minutes_per_month: version?.minutes_per_month ?? 0,
    max_workspaces: version?.max_workspaces ?? 0,
    max_agents_per_workspace: version?.max_agents_per_workspace ?? 0,
    max_users_per_workspace: version?.max_users_per_workspace ?? 0,
    overage_price_per_minute: Number(version?.overage_price_per_minute ?? 0),
    trial_days: version?.trial_days ?? 0,
    quota_period_anchor: version?.quota_period_anchor ?? "calendar_month",
  };
}

function publishPayload(values: PlanFormValues): PlanVersionPublishPayload {
  return {
    price_monthly: values.price_monthly.toFixed(2),
    executions_per_day: values.executions_per_day,
    executions_per_month: values.executions_per_month,
    minutes_per_day: values.minutes_per_day,
    minutes_per_month: values.minutes_per_month,
    max_workspaces: values.max_workspaces,
    max_agents_per_workspace: values.max_agents_per_workspace,
    max_users_per_workspace: values.max_users_per_workspace,
    overage_price_per_minute: values.overage_price_per_minute.toFixed(4),
    trial_days: values.trial_days,
    quota_period_anchor: values.quota_period_anchor,
    extras: {},
  };
}

function draftVersion(values: PlanFormValues, plan?: AdminPlan | null): PlanVersion {
  return {
    id: "draft",
    plan_id: plan?.id ?? "draft",
    version: (plan?.current_published_version ?? 0) + 1,
    published_at: null,
    deprecated_at: null,
    created_at: null,
    ...publishPayload(values),
  };
}

function errorMessage(error: unknown): string | null {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "Plan update failed";
}

export function PlanEditForm({ slug = "", mode = "edit", onFinished }: PlanEditFormProps) {
  const router = useRouter();
  const isCreate = mode === "create";
  const { data: plan, error, isLoading } = useAdminPlan(isCreate ? "" : slug);
  const createPlan = useCreatePlan();
  const publishVersion = usePublishPlanVersion();
  const updateMetadata = useUpdatePlanMetadata();
  const [pendingValues, setPendingValues] = useState<PlanFormValues | null>(null);
  const form = useForm<PlanFormValues>({
    resolver: zodResolver(planFormSchema),
    defaultValues: isCreate ? DEFAULT_VALUES : valuesFromPlan(plan),
  });

  useEffect(() => {
    if (!isCreate && plan) {
      form.reset(valuesFromPlan(plan));
    }
  }, [form, isCreate, plan]);

  const mutationError = errorMessage(createPlan.error ?? publishVersion.error ?? updateMetadata.error);
  const isPending = createPlan.isPending || publishVersion.isPending || updateMetadata.isPending;
  const previewVersion = useMemo(
    () => (pendingValues ? draftVersion(pendingValues, plan) : null),
    [pendingValues, plan],
  );

  async function commit(values: PlanFormValues) {
    const targetSlug = isCreate ? values.slug : slug;
    if (isCreate) {
      await createPlan.mutateAsync({
        slug: values.slug,
        display_name: values.display_name,
        description: values.description || null,
        tier: values.tier,
        is_public: values.is_public,
        is_active: values.is_active,
        allowed_model_tier: values.allowed_model_tier,
      });
    } else {
      await updateMetadata.mutateAsync({
        slug: targetSlug,
        payload: {
          display_name: values.display_name,
          description: values.description || null,
          is_public: values.is_public,
          is_active: values.is_active,
        },
      });
    }
    await publishVersion.mutateAsync({ slug: targetSlug, payload: publishPayload(values) });
    toast({ title: "Plan version published", variant: "success" });
    setPendingValues(null);
    onFinished?.();
    router.push(`/admin/plans/${targetSlug}/history`);
  }

  if (isLoading && !isCreate) {
    return <Skeleton className="h-96 w-full" />;
  }

  if (error && !isCreate) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Plan unavailable</AlertTitle>
        <AlertDescription>{errorMessage(error) ?? "Plan could not be loaded"}</AlertDescription>
      </Alert>
    );
  }

  return (
    <>
      <form
        className="space-y-5"
        onSubmit={form.handleSubmit((values) => setPendingValues(values))}
      >
        {mutationError ? (
          <Alert variant="destructive">
            <AlertTitle>Save failed</AlertTitle>
            <AlertDescription>{mutationError}</AlertDescription>
          </Alert>
        ) : null}

        <section className="grid gap-4 rounded-md border p-4 md:grid-cols-2">
          <Field label="Slug" error={form.formState.errors.slug?.message}>
            <Input disabled={!isCreate} {...form.register("slug")} />
          </Field>
          <Field label="Display name" error={form.formState.errors.display_name?.message}>
            <Input {...form.register("display_name")} />
          </Field>
          <Field label="Tier">
            <Select disabled={!isCreate} {...form.register("tier")}>
              <option value="free">Free</option>
              <option value="pro">Pro</option>
              <option value="enterprise">Enterprise</option>
            </Select>
          </Field>
          <Field label="Allowed model tier">
            <Select disabled={!isCreate} {...form.register("allowed_model_tier")}>
              <option value="cheap_only">Cheap only</option>
              <option value="standard">Standard</option>
              <option value="all">All</option>
            </Select>
          </Field>
          <Field label="Public">
            <Select {...form.register("is_public")}>
              <option value="true">Public</option>
              <option value="false">Hidden</option>
            </Select>
          </Field>
          <Field label="Active">
            <Select {...form.register("is_active")}>
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </Select>
          </Field>
          <div className="md:col-span-2">
            <Field label="Description">
              <Textarea {...form.register("description")} />
            </Field>
          </div>
        </section>

        <section className="grid gap-4 rounded-md border p-4 md:grid-cols-2 lg:grid-cols-3">
          <Field label="Monthly price EUR">
            <Input min={0} step="0.01" type="number" {...form.register("price_monthly")} />
          </Field>
          <Field label="Executions/day">
            <Input min={0} type="number" {...form.register("executions_per_day")} />
          </Field>
          <Field label="Executions/month">
            <Input min={0} type="number" {...form.register("executions_per_month")} />
          </Field>
          <Field label="Minutes/day">
            <Input min={0} type="number" {...form.register("minutes_per_day")} />
          </Field>
          <Field label="Minutes/month">
            <Input min={0} type="number" {...form.register("minutes_per_month")} />
          </Field>
          <Field label="Workspaces">
            <Input min={0} type="number" {...form.register("max_workspaces")} />
          </Field>
          <Field label="Agents/workspace">
            <Input min={0} type="number" {...form.register("max_agents_per_workspace")} />
          </Field>
          <Field label="Users/workspace">
            <Input min={0} type="number" {...form.register("max_users_per_workspace")} />
          </Field>
          <Field label="Overage EUR/min">
            <Input
              min={0}
              step="0.0001"
              type="number"
              {...form.register("overage_price_per_minute")}
            />
          </Field>
          <Field label="Trial days">
            <Input min={0} type="number" {...form.register("trial_days")} />
          </Field>
          <Field label="Period anchor">
            <Select {...form.register("quota_period_anchor")}>
              <option value="calendar_month">Calendar month</option>
              <option value="subscription_anniversary">Subscription anniversary</option>
            </Select>
          </Field>
        </section>

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => router.back()}>
            Cancel
          </Button>
          <Button disabled={isPending} type="submit">
            {isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Publish new version
          </Button>
        </div>
      </form>

      <Dialog open={pendingValues !== null} onOpenChange={(open) => !open && setPendingValues(null)}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>Publish new version</DialogTitle>
            <DialogDescription>
              Review the parameter diff before publishing this immutable plan version.
            </DialogDescription>
          </DialogHeader>
          {previewVersion ? (
            <PlanVersionDiff fromVersion={plan?.current_version ?? null} toVersion={previewVersion} />
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setPendingValues(null)}>
              Cancel
            </Button>
            <Button
              disabled={!pendingValues || isPending}
              type="button"
              onClick={() => pendingValues && commit(pendingValues)}
            >
              {isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Publish
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string | undefined;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
