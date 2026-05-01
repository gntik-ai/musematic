"use client";

import { useState } from "react";
import { RotateCcw } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useContextProfileVersions, useRollbackProfileVersion } from "@/lib/hooks/use-context-profile-versions";

interface VersionHistoryProps {
  workspaceId?: string | null;
  profileId?: string | null;
}

export function VersionHistory({ workspaceId, profileId }: VersionHistoryProps) {
  const t = useTranslations("creator.contextProfile");
  const versionsQuery = useContextProfileVersions(workspaceId, profileId);
  const rollback = useRollbackProfileVersion(workspaceId, profileId);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("versionHistory")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {(versionsQuery.data?.versions ?? []).map((version) => (
          <div
            key={version.id}
            className="flex flex-col gap-3 rounded-lg border p-3 md:flex-row md:items-center md:justify-between"
          >
            <div>
              <p className="font-medium">
                {t("version")} {version.version_number}
              </p>
              <p className="text-sm text-muted-foreground">
                {version.change_summary ?? t("noSummary")} · {version.created_at}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                type="button"
                variant={selectedVersion === version.version_number ? "secondary" : "outline"}
                onClick={() => setSelectedVersion(version.version_number)}
              >
                {t("compare")}
              </Button>
              <Button
                disabled={rollback.isPending}
                size="sm"
                type="button"
                variant="outline"
                onClick={() => rollback.mutate(version.version_number)}
              >
                <RotateCcw className="h-4 w-4" />
                {t("rollback")}
              </Button>
            </div>
          </div>
        ))}
        {selectedVersion ? (
          <pre className="max-h-80 overflow-auto rounded-lg bg-muted p-3 text-xs">
            {JSON.stringify(
              versionsQuery.data?.versions.find((item) => item.version_number === selectedVersion)
                ?.content_snapshot ?? {},
              null,
              2,
            )}
          </pre>
        ) : null}
      </CardContent>
    </Card>
  );
}
