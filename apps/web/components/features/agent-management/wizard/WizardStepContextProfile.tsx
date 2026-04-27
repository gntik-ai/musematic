"use client";

import type { CompositionBlueprint } from "@/lib/types/agent-management";

export function WizardStepContextProfile({ blueprint }: { blueprint: CompositionBlueprint }) {
  return (
    <section className="rounded-lg border p-5">
      <h2 className="text-xl font-semibold">Context Profile</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Configure profile sources for {blueprint.description || "this agent"} from the dedicated editor.
      </p>
    </section>
  );
}

