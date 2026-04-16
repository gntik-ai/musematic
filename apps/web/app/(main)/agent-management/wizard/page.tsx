"use client";

import { useEffect } from "react";
import { CompositionWizard } from "@/components/features/agent-management/CompositionWizard";
import { useCompositionWizardStore } from "@/lib/stores/use-composition-wizard-store";

export default function AgentCompositionWizardPage() {
  const reset = useCompositionWizardStore((state) => state.reset);

  useEffect(() => () => reset(), [reset]);

  return <CompositionWizard />;
}

