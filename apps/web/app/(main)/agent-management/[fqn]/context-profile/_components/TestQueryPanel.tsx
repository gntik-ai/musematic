"use client";

import { useState } from "react";
import { Play } from "lucide-react";
import { ProvenanceViewer } from "@/components/features/agents/ProvenanceViewer";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useContextProfilePreview } from "@/lib/hooks/use-context-profile-preview";

interface TestQueryPanelProps {
  workspaceId?: string | null;
  profileId?: string | null;
}

export function TestQueryPanel({ workspaceId, profileId }: TestQueryPanelProps) {
  const [queryText, setQueryText] = useState("customer support refund request");
  const preview = useContextProfilePreview(workspaceId, profileId);

  return (
    <div className="grid gap-4 lg:grid-cols-[0.9fr,1.1fr]">
      <div className="space-y-3 rounded-lg border p-4">
        <Textarea
          value={queryText}
          onChange={(event) => setQueryText(event.target.value)}
        />
        <Button
          disabled={!workspaceId || !profileId || preview.isPending}
          type="button"
          onClick={() => preview.mutate(queryText)}
        >
          <Play className="h-4 w-4" />
          Run Mock Preview
        </Button>
        {preview.data ? (
          <p className="text-sm text-muted-foreground">{preview.data.mock_response}</p>
        ) : null}
      </div>
      <ProvenanceViewer executionId={null} previewSources={preview.data?.sources ?? []} />
    </div>
  );
}

