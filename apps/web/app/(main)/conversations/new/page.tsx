"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

function NewConversationPageContent() {
  const searchParams = useSearchParams();
  const agent = searchParams.get("agent");
  const workspace = searchParams.get("workspace");
  const brief = searchParams.get("brief");

  return (
    <section className="space-y-6">
      <div>
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
          Conversations
        </p>
        <h1 className="mt-2 text-3xl font-semibold">New conversation</h1>
        <p className="mt-2 max-w-2xl text-muted-foreground">
          Marketplace invocation has already selected the agent and workspace for this draft.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {agent ? <Badge variant="outline">Agent: {agent}</Badge> : null}
        {workspace ? <Badge variant="outline">Workspace: {workspace}</Badge> : null}
      </div>

      <Card>
        <CardContent className="space-y-4 p-6">
          <div>
            <p className="text-sm font-medium">Task brief</p>
            <p className="mt-2 text-sm text-muted-foreground">
              {brief ?? "No task brief supplied."}
            </p>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

export default function NewConversationPage() {
  return (
    <Suspense fallback={<section className="space-y-6" />}>
      <NewConversationPageContent />
    </Suspense>
  );
}
