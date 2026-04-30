"use client";

import { useMemo } from "react";
import { Database, ShieldAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PreviewSource } from "@/lib/api/creator-uis";
import { useAppQuery } from "@/lib/hooks/use-api";
import { createApiClient } from "@/lib/api";

const api = createApiClient(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

interface ProvenanceViewerProps {
  executionId: string | null;
  previewSources?: PreviewSource[];
}

function classificationVariant(classification: string) {
  return ["pii", "phi", "financial", "confidential"].includes(classification)
    ? "destructive"
    : "secondary";
}

export function ProvenanceViewer({ executionId, previewSources = [] }: ProvenanceViewerProps) {
  const t = useTranslations("creator.provenance");
  const recordQuery = useAppQuery(
    ["context-provenance", executionId ?? "preview"],
    async () => {
      if (!executionId) {
        return null;
      }
      return api.get<{ provenance_chain?: Array<Record<string, unknown>> }>(
        `/api/v1/context-engineering/assembly-records/${encodeURIComponent(executionId)}`,
      );
    },
    { enabled: Boolean(executionId) },
  );

  const sources = useMemo<PreviewSource[]>(() => {
    if (!executionId) {
      return previewSources;
    }
    return (recordQuery.data?.provenance_chain ?? []).map((item, index) => ({
      origin: String(item.origin ?? `source-${index + 1}`),
      snippet: String(item.policy_justification ?? item.action ?? t("snippet")),
      score: Number(item.authority_score ?? 0),
      included: item.action !== "excluded",
      classification: String(item.data_classification ?? "public"),
      reason: item.action === "excluded" ? String(item.action) : null,
    }));
  }, [executionId, previewSources, recordQuery.data?.provenance_chain, t]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Database className="h-4 w-4" />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {sources.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("emptyAvailable")}</p>
        ) : null}
        {sources
          .slice()
          .sort((a, b) => b.score - a.score)
          .map((source) => (
            <div key={`${source.origin}-${source.snippet}`} className="rounded-lg border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium">{source.origin}</p>
                <div className="flex items-center gap-2">
                  <Badge variant={source.included ? "secondary" : "outline"}>
                    {source.included ? t("includedStatus") : t("excludedStatus")}
                  </Badge>
                  <Badge variant={classificationVariant(source.classification)}>
                    {classificationVariant(source.classification) === "destructive" ? (
                      <ShieldAlert className="h-3 w-3" />
                    ) : null}
                    {source.classification}
                  </Badge>
                  <span className="text-sm text-muted-foreground">
                    {(source.score * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{source.snippet}</p>
              {source.reason ? (
                <p className="mt-1 text-xs text-muted-foreground">{source.reason}</p>
              ) : null}
            </div>
          ))}
      </CardContent>
    </Card>
  );
}
