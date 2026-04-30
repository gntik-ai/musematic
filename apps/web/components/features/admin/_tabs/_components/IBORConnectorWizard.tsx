"use client";

import { useState } from "react";
import { CheckCircle2, Play, ServerCog } from "lucide-react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useCreateIBORConnector, useIBORSyncNow, useIBORTestConnection } from "@/lib/hooks/use-ibor-admin";
import type { IBORConnector, IBORConnectorCreate, TestConnectionResponse } from "@/lib/schemas/workspace-owner";
import { AttributeMappingWizard } from "./AttributeMappingWizard";

const steps = [
  "type",
  "connection",
  "test",
  "mapping",
  "schedule",
  "scope",
  "activate",
] as const;

export function IBORConnectorWizard({ onCreated }: { onCreated?: (connector: IBORConnector) => void }) {
  const t = useTranslations("admin.ibor.wizard");
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<IBORConnectorCreate>({
    name: t("defaultName"),
    source_type: "ldap",
    sync_mode: "pull",
    cadence_seconds: 3600,
    credential_ref: "secret/data/auth/ibor/corporate-directory",
    role_mapping_policy: [
      {
        directory_group: "platform-admins",
        platform_role: "platform_admin",
      },
    ],
    enabled: true,
  });
  const [created, setCreated] = useState<IBORConnector | null>(null);
  const [diagnostic, setDiagnostic] = useState<TestConnectionResponse | null>(null);
  const createConnector = useCreateIBORConnector();
  const testConnection = useIBORTestConnection();
  const syncNow = useIBORSyncNow();

  const connectorId = created?.id ?? null;

  async function handleCreate() {
    const connector = await createConnector.mutateAsync(form);
    setCreated(connector);
    onCreated?.(connector);
    setStep(2);
  }

  async function handleTest() {
    if (!connectorId) {
      return;
    }
    setDiagnostic(await testConnection.mutateAsync(connectorId));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ServerCog className="h-4 w-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <ol className="grid gap-2 md:grid-cols-7" aria-label={t("stepsAria")}>
          {steps.map((label, index) => (
            <li key={label}>
              <Button
                className="w-full justify-start gap-2"
                size="sm"
                type="button"
                variant={index === step ? "secondary" : "ghost"}
                onClick={() => setStep(index)}
              >
                {index < step ? <CheckCircle2 className="h-4 w-4" /> : null}
                {t(label)}
              </Button>
            </li>
          ))}
        </ol>

        {step === 0 ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ibor-name">{t("connectorName")}</Label>
              <Input
                id="ibor-name"
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>{t("directoryType")}</Label>
              <Select
                value={form.source_type}
                onChange={(event) =>
                  setForm({
                    ...form,
                    source_type: event.target.value as IBORConnectorCreate["source_type"],
                  })
                }
              >
                <option value="ldap">{t("types.ldap")}</option>
                <option value="oidc">{t("types.oidc")}</option>
                <option value="scim">{t("types.scim")}</option>
              </Select>
            </div>
          </div>
        ) : null}

        {step === 1 ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="ibor-secret-ref">{t("credentialReference")}</Label>
              <Input
                id="ibor-secret-ref"
                value={form.credential_ref}
                onChange={(event) =>
                  setForm({ ...form, credential_ref: event.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>{t("syncMode")}</Label>
              <Select
                value={form.sync_mode}
                onChange={(event) =>
                  setForm({
                    ...form,
                    sync_mode: event.target.value as IBORConnectorCreate["sync_mode"],
                  })
                }
              >
                <option value="pull">{t("syncModes.pull")}</option>
                <option value="push">{t("syncModes.push")}</option>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ibor-cadence">{t("cadenceSeconds")}</Label>
              <Input
                id="ibor-cadence"
                min={60}
                type="number"
                value={form.cadence_seconds}
                onChange={(event) =>
                  setForm({ ...form, cadence_seconds: Number(event.target.value) })
                }
              />
            </div>
            <Button
              className="md:col-span-2"
              disabled={createConnector.isPending}
              type="button"
              onClick={handleCreate}
            >
              {t("createDraft")}
            </Button>
          </div>
        ) : null}

        {step === 2 ? (
          <div className="space-y-4">
            <Button
              disabled={!connectorId || testConnection.isPending}
              type="button"
              onClick={handleTest}
            >
              <Play className="h-4 w-4" />
              {t("runDiagnostic")}
            </Button>
            <div className="grid gap-2">
              {(diagnostic?.steps ?? []).map((item) => (
                <div key={item.step} className="flex items-center justify-between rounded-md border p-3 text-sm">
                  <span>{item.step}</span>
                  <Badge variant={item.status === "success" ? "secondary" : "destructive"}>
                    {item.status} · {item.duration_ms}ms
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {step === 3 ? <AttributeMappingWizard /> : null}

        {step === 4 ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ibor-schedule">{t("cadenceSeconds")}</Label>
              <Input
                id="ibor-schedule"
                min={60}
                type="number"
                value={form.cadence_seconds}
                onChange={(event) =>
                  setForm({ ...form, cadence_seconds: Number(event.target.value) })
                }
              />
            </div>
            <div className="flex items-end gap-3 rounded-md border p-3">
              <Switch
                aria-label={t("enableConnector")}
                checked={form.enabled}
                onCheckedChange={(enabled) => setForm({ ...form, enabled })}
              />
              <span className="text-sm">{t("enabledAfterActivation")}</span>
            </div>
          </div>
        ) : null}

        {step === 5 ? (
          <div className="rounded-md border p-3 text-sm text-muted-foreground">
            {t("scopeDescription")}
          </div>
        ) : null}

        {step === 6 ? (
          <div className="flex flex-col gap-3 rounded-md border p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-medium">{created?.name ?? form.name}</p>
              <p className="text-sm text-muted-foreground">
                {created ? t("draftCreated") : t("draftRequired")}
              </p>
            </div>
            <Button
              disabled={!connectorId || syncNow.isPending}
              type="button"
              onClick={() => connectorId && syncNow.mutate(connectorId)}
            >
              {t("syncNow")}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
