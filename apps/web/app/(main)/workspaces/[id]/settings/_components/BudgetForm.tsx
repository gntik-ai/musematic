"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useWorkspaceSettingsMutation } from "@/lib/hooks/use-workspace-settings";
import type { WorkspaceSettings } from "@/lib/schemas/workspace-owner";

export function BudgetForm({ workspaceId, settings }: { workspaceId: string; settings: WorkspaceSettings }) {
  const mutation = useWorkspaceSettingsMutation(workspaceId);
  const t = useTranslations("workspaces.settings.budget");
  const initialAmount = useMemo(() => Number(settings.cost_budget.amount ?? 0), [settings.cost_budget]);
  const [amount, setAmount] = useState(initialAmount);
  const [hardCap, setHardCap] = useState(Boolean(settings.cost_budget.hard_cap_enabled));

  return (
    <Card>
      <CardHeader><CardTitle>{t("title")}</CardTitle></CardHeader>
      <CardContent>
        <form
          className="grid gap-4 md:grid-cols-[1fr_auto]"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate({ cost_budget: { ...settings.cost_budget, amount, hard_cap_enabled: hardCap } });
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="budget-amount">{t("monthlyLimit")}</Label>
            <Input id="budget-amount" min={0} onChange={(event) => setAmount(Number(event.target.value))} type="number" value={amount} />
          </div>
          <div className="flex items-end gap-3">
            <Label className="pb-2" htmlFor="budget-hard-cap">{t("hardCap")}</Label>
            <Switch checked={hardCap} id="budget-hard-cap" onCheckedChange={setHardCap} />
          </div>
          <Button className="md:col-span-2" disabled={mutation.isPending} type="submit">
            {t("save")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
