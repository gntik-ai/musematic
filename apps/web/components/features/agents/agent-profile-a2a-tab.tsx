"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CodeBlock } from "@/components/shared/CodeBlock";
import { useA2aAgentCard } from "@/lib/hooks/use-a2a-agent-card";

export interface AgentProfileA2aTabProps {
  agentId: string;
}

export function AgentProfileA2aTab({ agentId }: AgentProfileA2aTabProps) {
  const { card, isLoading } = useA2aAgentCard(agentId);

  if (isLoading) {
    return <div className="h-40 animate-pulse rounded-2xl bg-muted/50" />;
  }

  if (!card) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>A2A profile</CardTitle>
          <CardDescription>No A2A card is published for this agent yet.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline">Configure</Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>A2A profile</CardTitle>
        <CardDescription>Review the published agent card and copy it when needed.</CardDescription>
      </CardHeader>
      <CardContent>
        <CodeBlock code={JSON.stringify(card, null, 2)} language="json" maxHeight={420} />
      </CardContent>
    </Card>
  );
}
