"use client";

import type { CompositionBlueprint } from "@/lib/types/agent-management";

export function WizardStepAttachBoth({ blueprint }: { blueprint: CompositionBlueprint }) {
  return (
    <section className="rounded-lg border p-5">
      <h2 className="text-xl font-semibold">Attach Both</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Attach the selected context profile and contract before publishing{" "}
        {blueprint.description || "this agent"}.
      </p>
    </section>
  );
}

