"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useWorkspaceSettingsMutation } from "@/lib/hooks/use-workspace-settings";
import type { WorkspaceSettings } from "@/lib/schemas/workspace-owner";

const fields = ["agents", "fleets", "executions", "storage_gb"] as const;

export function QuotaConfigForm({ workspaceId, settings }: { workspaceId: string; settings: WorkspaceSettings }) {
  const mutation = useWorkspaceSettingsMutation(workspaceId);
  const t = useTranslations("workspaces.settings.quotas");
  const [values, setValues] = useState<Record<string, number>>(() =>
    Object.fromEntries(fields.map((field) => [field, Number(settings.quota_config[field] ?? 0)])),
  );

  return (
    <Card>
      <CardHeader><CardTitle>{t("title")}</CardTitle></CardHeader>
      <CardContent>
        <form
          className="grid gap-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate({ quota_config: values });
          }}
        >
          {fields.map((field) => (
            <div key={field} className="space-y-2">
              <Label htmlFor={`quota-${field}`}>{t(`fields.${field}`)}</Label>
              <Input
                id={`quota-${field}`}
                min={0}
                onChange={(event) => setValues((current) => ({ ...current, [field]: Number(event.target.value) }))}
                type="number"
                value={values[field] ?? 0}
              />
            </div>
          ))}
          <Button className="md:col-span-2" disabled={mutation.isPending} type="submit">
            {t("save")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
