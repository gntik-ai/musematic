"use client";

import { useParams } from "next/navigation";
import { Tags } from "lucide-react";
import { useTranslations } from "next-intl";
import { WorkspaceOwnerLayout } from "@/components/layout/WorkspaceOwnerLayout";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useEntityLabels, useEntityTags } from "@/lib/api/tagging";

export default function WorkspaceTagsPage() {
  const params = useParams<{ id: string }>();
  const tags = useEntityTags("workspace", params.id);
  const labels = useEntityLabels("workspace", params.id);
  const t = useTranslations("workspaces.tags");

  return (
    <WorkspaceOwnerLayout title={t("title")} description={t("description")}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Tags className="h-4 w-4" />
            {t("cardTitle")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div>
            <h2 className="mb-2 text-sm font-medium">{t("tags")}</h2>
            <div className="flex flex-wrap gap-2">
              {(tags.data?.tags ?? []).map((tag) => <Badge key={tag.tag}>{tag.tag}</Badge>)}
              {tags.data?.tags.length === 0 ? (
                <span className="text-sm text-muted-foreground">{t("noTags")}</span>
              ) : null}
            </div>
          </div>
          <div>
            <h2 className="mb-2 text-sm font-medium">{t("labels")}</h2>
            <div className="flex flex-wrap gap-2">
              {(labels.data?.labels ?? []).map((label) => (
                <Badge key={`${label.key}:${label.value}`} variant="outline">{label.key}: {label.value}</Badge>
              ))}
              {labels.data?.labels.length === 0 ? (
                <span className="text-sm text-muted-foreground">{t("noLabels")}</span>
              ) : null}
            </div>
          </div>
        </CardContent>
      </Card>
    </WorkspaceOwnerLayout>
  );
}
