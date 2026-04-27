"use client";

import type { CompositionBlueprint } from "@/lib/types/agent-management";

export function WizardStepTestProfile({ blueprint }: { blueprint: CompositionBlueprint }) {
  return (
    <section className="rounded-lg border p-5">
      <h2 className="text-xl font-semibold">Test Profile</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Run mock retrieval previews before publishing {blueprint.description || "the agent"}.
      </p>
    </section>
  );
}

