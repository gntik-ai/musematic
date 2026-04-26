"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import type { WorkspaceBudgetRequest } from "@/lib/api/costs";

function parseThresholds(value: string): number[] {
  return value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item));
}

export const budgetConfigSchema = z.object({
  period_type: z.enum(["daily", "weekly", "monthly"]),
  budget_cents: z.coerce.number().int().positive(),
  thresholds: z
    .string()
    .min(1)
    .refine((value) => parseThresholds(value).length > 0, "threshold_required")
    .refine(
      (value) => parseThresholds(value).every((item) => item > 0 && item <= 100),
      "threshold_range",
    )
    .refine(
      (value) => {
        const items = parseThresholds(value);
        return items.every((item, index) => index === 0 || item >= (items[index - 1] ?? 0));
      },
      "threshold_order",
    ),
  hard_cap_enabled: z.boolean(),
  admin_override_enabled: z.boolean(),
});

type BudgetFormValues = z.infer<typeof budgetConfigSchema>;

interface BudgetConfigFormProps {
  defaultValues?: Partial<WorkspaceBudgetRequest>;
  isSubmitting?: boolean;
  onSubmit: (payload: WorkspaceBudgetRequest) => void;
}

export function BudgetConfigForm({
  defaultValues,
  isSubmitting = false,
  onSubmit,
}: BudgetConfigFormProps) {
  const form = useForm<BudgetFormValues>({
    resolver: zodResolver(budgetConfigSchema),
    defaultValues: {
      period_type: defaultValues?.period_type ?? "monthly",
      budget_cents: defaultValues?.budget_cents ?? 10000,
      thresholds: (defaultValues?.soft_alert_thresholds ?? [50, 80, 100]).join(", "),
      hard_cap_enabled: defaultValues?.hard_cap_enabled ?? false,
      admin_override_enabled: defaultValues?.admin_override_enabled ?? true,
    },
  });

  return (
    <form
      className="space-y-4"
      onSubmit={form.handleSubmit((values) => {
        onSubmit({
          period_type: values.period_type,
          budget_cents: values.budget_cents,
          soft_alert_thresholds: parseThresholds(values.thresholds),
          hard_cap_enabled: values.hard_cap_enabled,
          admin_override_enabled: values.admin_override_enabled,
          currency: defaultValues?.currency ?? "USD",
        });
      })}
    >
      <div className="space-y-2">
        <Label htmlFor="period_type">Period</Label>
        <Select
          id="period_type"
          value={form.watch("period_type")}
          onChange={(event) =>
            form.setValue("period_type", event.target.value as BudgetFormValues["period_type"])
          }
        >
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="monthly">Monthly</option>
        </Select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="budget_cents">Budget cents</Label>
        <Input id="budget_cents" type="number" {...form.register("budget_cents")} />
      </div>
      <div className="space-y-2">
        <Label htmlFor="thresholds">Thresholds</Label>
        <Input id="thresholds" placeholder="50, 80, 100" {...form.register("thresholds")} />
        {form.formState.errors.thresholds ? (
          <p className="text-xs text-destructive">Use ascending values no greater than 100.</p>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <Checkbox
          checked={form.watch("hard_cap_enabled")}
          id="hard_cap_enabled"
          onChange={(event) => form.setValue("hard_cap_enabled", event.target.checked)}
        />
        <Label htmlFor="hard_cap_enabled">Hard cap</Label>
      </div>
      <div className="flex items-center gap-2">
        <Checkbox
          checked={form.watch("admin_override_enabled")}
          id="admin_override_enabled"
          onChange={(event) => form.setValue("admin_override_enabled", event.target.checked)}
        />
        <Label htmlFor="admin_override_enabled">Admin override</Label>
      </div>
      <Button disabled={isSubmitting} type="submit">
        Save
      </Button>
    </form>
  );
}
