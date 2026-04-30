"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";

const presets = {
  active_directory: { email: "mail", display_name: "displayName", groups: "memberOf" },
  openldap: { email: "mail", display_name: "cn", groups: "memberOf" },
  freeipa: { email: "mail", display_name: "displayName", groups: "memberOf" },
} as const;

export function AttributeMappingWizard() {
  const [preset, setPreset] = useState<keyof typeof presets>("active_directory");
  const mapping = presets[preset];

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Attribute mapping</CardTitle></CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2 md:col-span-2">
          <Label>Vendor preset</Label>
          <Select
            value={preset}
            onChange={(event) => setPreset(event.target.value as keyof typeof presets)}
          >
            <option value="active_directory">Active Directory</option>
            <option value="openldap">OpenLDAP</option>
            <option value="freeipa">FreeIPA</option>
          </Select>
        </div>
        {Object.entries(mapping).map(([target, source]) => (
          <div key={target} className="space-y-2">
            <Label>{target}</Label>
            <Input readOnly value={source} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
