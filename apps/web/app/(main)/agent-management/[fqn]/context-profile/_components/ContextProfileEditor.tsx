"use client";

import { useMemo, useState } from "react";
import { History, Save } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { SchemaValidatedEditor } from "@/components/features/agents/SchemaValidatedEditor";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type ContextProfilePayload } from "@/lib/api/creator-uis";
import { useContextProfileSave } from "@/lib/hooks/use-context-profile-save";
import { useProfileSchema } from "@/lib/hooks/use-profile-schema";
import { useToast } from "@/lib/hooks/use-toast";
import { useWorkspaceStore } from "@/store/workspace-store";
import { ContextBudgetControls } from "./ContextBudgetControls";
import { RerankingRulesEditor } from "./RerankingRulesEditor";
import { RetrievalStrategySelector } from "./RetrievalStrategySelector";
import { SourcePicker } from "./SourcePicker";
import { TestQueryPanel } from "./TestQueryPanel";

interface ContextProfileEditorProps {
  fqn: string;
}

const DEFAULT_PROFILE = {
  name: "default-context-profile",
  description: "Creator-authored profile",
  source_config: [
    {
      source_type: "long_term_memory",
      priority: 70,
      enabled: true,
      max_elements: 10,
      retrieval_strategy: "hybrid",
      provenance_enabled: true,
      provenance_classification: "public",
      provenance_attribution: "Workspace memory",
    },
  ],
  budget_config: { max_tokens_step: 8192, max_sources: 9 },
  compaction_strategies: ["relevance_truncation", "priority_eviction"],
  quality_weights: {},
  privacy_overrides: {},
  is_default: false,
};

export function ContextProfileEditor({ fqn }: ContextProfileEditorProps) {
  const t = useTranslations("creator.contextProfile");
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const { toast } = useToast();
  const schemaQuery = useProfileSchema();
  const [profileId, setProfileId] = useState("");
  const [profileJson, setProfileJson] = useState(() => JSON.stringify(DEFAULT_PROFILE, null, 2));
  const [activeTab, setActiveTab] = useState<"editor" | "sources" | "test">("editor");
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveMutation = useContextProfileSave(workspaceId, profileId || null);

  const encodedFqn = useMemo(() => encodeURIComponent(fqn), [fqn]);

  const handleSave = async () => {
    setSaveError(null);

    let payload: ContextProfilePayload;
    try {
      const parsed = JSON.parse(profileJson) as unknown;
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error(t("invalidObject"));
      }
      payload = parsed as ContextProfilePayload;
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : t("invalidJson"));
      return;
    }

    try {
      const saved = await saveMutation.mutateAsync(payload);
      setProfileId(saved.id);
      toast({
        title: profileId ? t("updated") : t("created"),
        description: saved.name,
        variant: "success",
      });
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : t("saveFailure"));
    }
  };

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 border-b pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase text-brand-accent">{fqn}</p>
          <h1 className="mt-2 text-3xl font-semibold">{t("title")}</h1>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
            {t("description")}
          </p>
        </div>
        <Button asChild variant="outline">
          <Link href={`/agent-management/${encodedFqn}/context-profile/history`}>
            <History className="h-4 w-4" />
            {t("history")}
          </Link>
        </Button>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <Tabs className="space-y-4">
          <TabsList>
            <TabsTrigger
              className={activeTab === "editor" ? "bg-background" : undefined}
              onClick={() => setActiveTab("editor")}
            >
              {t("editor")}
            </TabsTrigger>
            <TabsTrigger
              className={activeTab === "sources" ? "bg-background" : undefined}
              onClick={() => setActiveTab("sources")}
            >
              {t("sources")}
            </TabsTrigger>
            <TabsTrigger
              className={activeTab === "test" ? "bg-background" : undefined}
              onClick={() => setActiveTab("test")}
            >
              {t("test")}
            </TabsTrigger>
          </TabsList>
          {activeTab === "editor" ? (
            <TabsContent>
              <SchemaValidatedEditor
                defaultLanguage="json"
                isSchemaLoading={schemaQuery.isLoading}
                label={t("profileJson")}
                schema={schemaQuery.data}
                value={profileJson}
                onChange={setProfileJson}
              />
            </TabsContent>
          ) : null}
          {activeTab === "sources" ? (
            <TabsContent>
              <div className="space-y-4">
                <SourcePicker />
                <RetrievalStrategySelector />
                <RerankingRulesEditor />
                <ContextBudgetControls />
              </div>
            </TabsContent>
          ) : null}
          {activeTab === "test" ? (
            <TabsContent>
              <TestQueryPanel profileId={profileId} workspaceId={workspaceId} />
            </TabsContent>
          ) : null}
        </Tabs>

        <Card>
          <CardHeader>
            <CardTitle>{t("profileControls")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="profile-id">{t("profileId")}</Label>
              <Input
                id="profile-id"
                placeholder={t("profileIdPlaceholder")}
                value={profileId}
                onChange={(event) => setProfileId(event.target.value)}
              />
            </div>
            {saveError ? (
              <Alert variant="destructive">
                <AlertDescription>{saveError}</AlertDescription>
              </Alert>
            ) : null}
            <Button
              className="w-full"
              disabled={!workspaceId || saveMutation.isPending}
              type="button"
              onClick={() => {
                void handleSave();
              }}
            >
              <Save className="h-4 w-4" />
              {saveMutation.isPending ? t("saving") : profileId ? t("update") : t("create")}
            </Button>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
