"use client";

import { AgentIdentityForm } from "@/components/features/agents/agent-identity-form";

export default function CreateAgentPage() {
  return (
    <section className="space-y-6">
      <AgentIdentityForm
        description="Define the FQN identity, operational purpose, and initial visibility rules for a new agent."
        mode="create"
        title="Create Agent"
      />
    </section>
  );
}
