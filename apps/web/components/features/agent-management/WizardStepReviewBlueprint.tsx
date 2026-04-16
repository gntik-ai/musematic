"use client";

import { ChevronDown, MessageSquareText } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import type { BlueprintItem, CompositionBlueprint } from "@/lib/types/agent-management";

interface WizardStepReviewBlueprintProps {
  blueprint: CompositionBlueprint;
}

function confidenceBadgeClass(confidence: number): string {
  if (confidence < 0.5) {
    return "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }

  return "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300";
}

function formatBlueprintValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join(", ") : "No values provided.";
  }

  if (typeof value === "object" && value !== null) {
    return JSON.stringify(value, null, 2);
  }

  return String(value);
}

function BlueprintSection({
  item,
  title,
}: {
  item: BlueprintItem<unknown>;
  title: string;
}) {
  return (
    <details className="group rounded-2xl border border-border/60 bg-background/70 p-4" open>
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
        <div className="space-y-1">
          <p className="font-medium">{title}</p>
          <Badge className={confidenceBadgeClass(item.confidence)} variant="outline">
            Confidence {(item.confidence * 100).toFixed(0)}%
          </Badge>
        </div>
        <ChevronDown className="h-4 w-4 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-4 space-y-4 text-sm">
        {item.confidence < 0.5 ? (
          <Alert className="border-amber-500/30 bg-amber-500/10">
            <AlertTitle>Low confidence recommendation</AlertTitle>
            <AlertDescription>
              This recommendation is below 50% confidence. Review the reasoning carefully before
              accepting it.
            </AlertDescription>
          </Alert>
        ) : null}
        <div>
          <p className="font-medium text-foreground">Proposed value</p>
          <pre className="mt-2 overflow-x-auto rounded-xl border border-border/60 bg-card/80 p-4 text-xs text-muted-foreground">
            {formatBlueprintValue(item.value)}
          </pre>
        </div>
        <div>
          <p className="font-medium text-foreground">AI reasoning</p>
          <p className="mt-2 text-muted-foreground">{item.reasoning}</p>
        </div>
      </div>
    </details>
  );
}

export function WizardStepReviewBlueprint({
  blueprint,
}: WizardStepReviewBlueprintProps) {
  return (
    <div className="space-y-6 rounded-3xl border border-border/60 bg-card/80 p-6 shadow-sm">
      <div className="space-y-2">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
          Step 2
        </p>
        <h2 className="text-2xl font-semibold">Review the generated blueprint</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Each recommendation includes the AI&apos;s reasoning and a confidence signal before you move
          into customization.
        </p>
      </div>

      {blueprint.follow_up_questions.length > 0 ? (
        <Alert>
          <MessageSquareText className="h-4 w-4" />
          <AlertTitle>Follow-up questions</AlertTitle>
          <div className="mt-2 text-sm text-muted-foreground">
            <ul className="space-y-1">
              {blueprint.follow_up_questions.map((question) => (
                <li key={question}>• {question}</li>
              ))}
            </ul>
          </div>
        </Alert>
      ) : null}

      <div className="space-y-4">
        <BlueprintSection item={blueprint.model_config} title="Model configuration" />
        <BlueprintSection item={blueprint.tool_selections} title="Tool selections" />
        <BlueprintSection item={blueprint.connector_suggestions} title="Connector suggestions" />
        <BlueprintSection item={blueprint.policy_recommendations} title="Policy recommendations" />
        <BlueprintSection item={blueprint.context_profile} title="Context profile" />
      </div>
    </div>
  );
}
