"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useWorkspaceSettingsMutation } from "@/lib/hooks/use-workspace-settings";
import type { WorkspaceSettings } from "@/lib/schemas/workspace-owner";

export function DLPRulesForm({ workspaceId, settings }: { workspaceId: string; settings: WorkspaceSettings }) {
  const mutation = useWorkspaceSettingsMutation(workspaceId);
  const t = useTranslations("workspaces.settings.dlp");
  const [enabled, setEnabled] = useState(Boolean(settings.dlp_rules.enabled ?? true));
  const [rulesText, setRulesText] = useState(
    Array.isArray(settings.dlp_rules.rule_ids) ? settings.dlp_rules.rule_ids.join("\n") : "",
  );

  return (
    <Card>
      <CardHeader><CardTitle>{t("title")}</CardTitle></CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            mutation.mutate({
              dlp_rules: {
                ...settings.dlp_rules,
                enabled,
                rule_ids: rulesText.split("\n").map((item) => item.trim()).filter(Boolean),
              },
            });
          }}
        >
          <div className="flex items-center gap-3">
            <Switch checked={enabled} id="dlp-enabled" onCheckedChange={setEnabled} />
            <Label htmlFor="dlp-enabled">{t("enabled")}</Label>
          </div>
          <div className="space-y-2">
            <Label htmlFor="dlp-rule-ids">{t("ruleIds")}</Label>
            <Textarea id="dlp-rule-ids" onChange={(event) => setRulesText(event.target.value)} value={rulesText} />
          </div>
          <Button disabled={mutation.isPending} type="submit">{t("save")}</Button>
        </form>
      </CardContent>
    </Card>
  );
}
