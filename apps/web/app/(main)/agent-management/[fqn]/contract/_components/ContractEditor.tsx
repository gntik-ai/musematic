"use client";

import { useState } from "react";
import { Save } from "lucide-react";
import { SchemaValidatedEditor } from "@/components/features/agents/SchemaValidatedEditor";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type AgentContractPayload } from "@/lib/api/creator-uis";
import { useContractSave } from "@/lib/hooks/use-contract-save";
import { useContractSchema } from "@/lib/hooks/use-contract-schema";
import { useToast } from "@/lib/hooks/use-toast";
import { useSchemaEnums } from "@/lib/hooks/use-schema-enums";
import { AttachToRevisionDialog } from "./AttachToRevisionDialog";
import { ContractPreviewPanel } from "./ContractPreviewPanel";

const DEFAULT_CONTRACT = {
  agent_id: "",
  task_scope: "Answer customer questions using approved sources.",
  expected_outputs: { required: ["answer", "citations"] },
  quality_thresholds: { minimum_confidence: 0.72 },
  escalation_conditions: { pii_detected: "escalate" },
  success_criteria: { must_include_citation: true },
  enforcement_policy: "warn",
};

export function ContractEditor({ fqn }: { fqn: string }) {
  const { toast } = useToast();
  const schemaQuery = useContractSchema();
  const enumsQuery = useSchemaEnums();
  const [contractId, setContractId] = useState("");
  const [contractText, setContractText] = useState(() =>
    JSON.stringify({ ...DEFAULT_CONTRACT, agent_id: fqn }, null, 2),
  );
  const [activeTab, setActiveTab] = useState<"editor" | "preview">("editor");
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveMutation = useContractSave(contractId || null);

  const handleSave = async () => {
    setSaveError(null);

    let payload: AgentContractPayload;
    try {
      const parsed = JSON.parse(contractText) as unknown;
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        throw new Error("Contract JSON must be an object.");
      }
      payload = parsed as AgentContractPayload;
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Contract JSON is invalid.");
      return;
    }

    try {
      const saved = await saveMutation.mutateAsync(payload);
      setContractId(saved.id);
      toast({
        title: contractId ? "Contract updated" : "Contract created",
        description: saved.agent_id,
        variant: "success",
      });
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : "Unable to save contract.");
    }
  };

  return (
    <section className="space-y-6">
      <div className="border-b pb-5">
        <p className="text-xs font-semibold uppercase text-brand-accent">{fqn}</p>
        <h1 className="mt-2 text-3xl font-semibold">Agent Contract</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Author behavioral terms, preview enforcement, and attach contracts to revisions.
        </p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
        <Tabs className="space-y-4">
          <TabsList>
            <TabsTrigger
              className={activeTab === "editor" ? "bg-background" : undefined}
              onClick={() => setActiveTab("editor")}
            >
              Editor
            </TabsTrigger>
            <TabsTrigger
              className={activeTab === "preview" ? "bg-background" : undefined}
              onClick={() => setActiveTab("preview")}
            >
              Preview
            </TabsTrigger>
          </TabsList>
          {activeTab === "editor" ? (
            <TabsContent>
              <SchemaValidatedEditor
                defaultLanguage="json"
                enableLanguageToggle
                isSchemaLoading={schemaQuery.isLoading}
                label="Contract"
                schema={schemaQuery.data}
                value={contractText}
                onChange={setContractText}
              />
            </TabsContent>
          ) : null}
          {activeTab === "preview" ? (
            <TabsContent>
              <ContractPreviewPanel contractId={contractId} />
            </TabsContent>
          ) : null}
        </Tabs>

        <Card>
          <CardHeader>
            <CardTitle>Contract Controls</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="contract-id">Contract ID</Label>
              <Input
                id="contract-id"
                placeholder="Paste existing contract UUID"
                value={contractId}
                onChange={(event) => setContractId(event.target.value)}
              />
            </div>
            <div className="rounded-lg border p-3 text-sm">
              <p className="font-medium">Schema enums</p>
              <p className="mt-1 text-muted-foreground">
                {(enumsQuery.data?.role_types ?? []).slice(0, 6).join(", ") || "Loading"}
              </p>
            </div>
            <AttachToRevisionDialog contractId={contractId} />
            {saveError ? (
              <Alert variant="destructive">
                <AlertDescription>{saveError}</AlertDescription>
              </Alert>
            ) : null}
            <Button
              className="w-full"
              disabled={saveMutation.isPending}
              type="button"
              onClick={() => {
                void handleSave();
              }}
            >
              <Save className="h-4 w-4" />
              {saveMutation.isPending ? "Saving" : contractId ? "Update Contract" : "Create Contract"}
            </Button>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
