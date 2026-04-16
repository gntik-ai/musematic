"use client";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Textarea } from "@/components/ui/textarea";
import type { CompositionBlueprint } from "@/lib/types/agent-management";
import { useCompositionWizardStore } from "@/lib/stores/use-composition-wizard-store";

interface WizardStepCustomizeProps {
  blueprint: CompositionBlueprint;
}

function stringifyObject(value: Record<string, unknown>): string {
  return JSON.stringify(value, null, 2);
}

function parseJsonObject(value: string): Record<string, unknown> {
  if (!value.trim()) {
    return {};
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

function toLines(value: string[]): string {
  return value.join("\n");
}

function parseLines(value: string): string[] {
  return value
    .split("\n")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function WizardStepCustomize({
  blueprint,
}: WizardStepCustomizeProps) {
  const applyCustomization = useCompositionWizardStore(
    (state) => state.applyCustomization,
  );
  const customizations = useCompositionWizardStore((state) => state.customizations);

  const currentTools = customizations.tool_selections ?? blueprint.tool_selections.value;
  const removedPurposeCriticalTools = blueprint.tool_selections.value.filter(
    (tool) => !currentTools.includes(tool),
  );

  return (
    <div className="space-y-6 rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
      <div className="space-y-2">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
          Step 3
        </p>
        <h2 className="text-2xl font-semibold">Customize the blueprint</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Refine the proposed model, tool, connector, and policy choices before validation.
        </p>
      </div>

      {removedPurposeCriticalTools.length > 0 ? (
        <Alert className="border-amber-500/30 bg-amber-500/10">
          <AlertTitle>Tool selection diverges from the original blueprint</AlertTitle>
          <AlertDescription>
            Removing {removedPurposeCriticalTools.join(", ")} may affect the agent&apos;s ability to
            fulfill the described purpose.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <label className="space-y-2 text-sm">
          <span className="font-medium">Model configuration (JSON)</span>
          <Textarea
            aria-label="Model configuration"
            className="min-h-56 font-mono text-xs"
            value={stringifyObject(customizations.model_config ?? blueprint.model_config.value)}
            onChange={(event) =>
              applyCustomization("model_config", parseJsonObject(event.target.value))
            }
          />
        </label>

        <label className="space-y-2 text-sm">
          <span className="font-medium">Tool selections</span>
          <Textarea
            aria-label="Tool selections"
            className="min-h-56"
            value={toLines(currentTools)}
            onChange={(event) =>
              applyCustomization("tool_selections", parseLines(event.target.value))
            }
          />
        </label>

        <label className="space-y-2 text-sm">
          <span className="font-medium">Connector suggestions</span>
          <Textarea
            aria-label="Connector suggestions"
            className="min-h-44"
            value={toLines(
              customizations.connector_suggestions ?? blueprint.connector_suggestions.value,
            )}
            onChange={(event) =>
              applyCustomization("connector_suggestions", parseLines(event.target.value))
            }
          />
        </label>

        <label className="space-y-2 text-sm">
          <span className="font-medium">Policy recommendations</span>
          <Textarea
            aria-label="Policy recommendations"
            className="min-h-44"
            value={toLines(
              customizations.policy_recommendations ?? blueprint.policy_recommendations.value,
            )}
            onChange={(event) =>
              applyCustomization("policy_recommendations", parseLines(event.target.value))
            }
          />
        </label>
      </div>
    </div>
  );
}
