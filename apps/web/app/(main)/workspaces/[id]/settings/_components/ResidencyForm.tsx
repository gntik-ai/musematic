"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { useWorkspaceSettingsMutation } from "@/lib/hooks/use-workspace-settings";
import type { WorkspaceSettings } from "@/lib/schemas/workspace-owner";

export function ResidencyForm({ workspaceId, settings }: { workspaceId: string; settings: WorkspaceSettings }) {
  const mutation = useWorkspaceSettingsMutation(workspaceId);
  const [region, setRegion] = useState(String(settings.residency_config.region ?? ""));
  const [tier, setTier] = useState(String(settings.residency_config.tier ?? "standard"));

  return (
    <Card>
      <CardHeader><CardTitle>Residency</CardTitle></CardHeader>
      <CardContent>
        <form
          className="grid gap-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate({ residency_config: { ...settings.residency_config, region, tier } });
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="residency-region">Region</Label>
            <Input id="residency-region" onChange={(event) => setRegion(event.target.value)} placeholder="eu-west-1" value={region} />
          </div>
          <div className="space-y-2">
            <Label>Tier</Label>
            <Select value={tier} onChange={(event) => setTier(event.target.value)}>
              <option value="standard">standard</option>
              <option value="restricted">restricted</option>
              <option value="regulated">regulated</option>
            </Select>
          </div>
          <Button className="md:col-span-2" disabled={mutation.isPending} type="submit">Save residency</Button>
        </form>
      </CardContent>
    </Card>
  );
}
