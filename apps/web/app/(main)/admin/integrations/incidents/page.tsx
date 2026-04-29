"use client";

import { useState } from "react";
import { IntegrationConfigForm } from "@/components/features/incident-response";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  createIntegration,
  deleteIntegration,
  updateIntegration,
  useIntegrations,
  type IntegrationCreateRequest,
  type IntegrationResponse,
} from "@/lib/api/incidents";
import { useAppMutation } from "@/lib/hooks/use-api";

export default function AdminIncidentIntegrationsPage() {
  const integrations = useIntegrations();
  const [selected, setSelected] = useState<IntegrationResponse | null>(null);
  const create = useAppMutation(createIntegration);
  const update = useAppMutation((payload: IntegrationCreateRequest & { id: string }) =>
    updateIntegration(payload.id, {
      enabled: payload.enabled,
      alert_severity_mapping: payload.alert_severity_mapping,
    }),
  );
  const remove = useAppMutation(deleteIntegration);
  return (
    <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Incident integrations</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {integrations.data?.map((integration) => (
            <div key={integration.id} className="flex items-center justify-between gap-3 rounded-md border p-3">
              <div>
                <p className="font-medium">{integration.provider}</p>
                <p className="text-xs text-muted-foreground">{integration.integration_key_ref}</p>
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setSelected(integration)}>
                  Edit
                </Button>
                <Button size="sm" variant="outline" onClick={() => remove.mutate(integration.id)}>
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{selected ? "Edit integration" : "Create integration"}</CardTitle>
        </CardHeader>
        <CardContent>
          <IntegrationConfigForm
            integration={selected}
            isSaving={create.isPending || update.isPending}
            onSubmit={(payload) =>
              selected ? update.mutate({ ...payload, id: selected.id }) : create.mutate(payload)
            }
          />
        </CardContent>
      </Card>
    </section>
  );
}
