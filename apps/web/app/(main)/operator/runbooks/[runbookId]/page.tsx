"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { RunbookEditor, RunbookViewer } from "@/components/features/incident-response";
import { updateRunbook, useRunbook } from "@/lib/api/incidents";
import { useAppMutation } from "@/lib/hooks/use-api";

export default function OperatorRunbookDetailPage() {
  const params = useParams<{ runbookId: string }>();
  const [editing, setEditing] = useState(false);
  const [staleVersion, setStaleVersion] = useState<number | null>(null);
  const runbook = useRunbook(params.runbookId);
  const save = useAppMutation((payload: Parameters<typeof updateRunbook>[1]) =>
    updateRunbook(params.runbookId, payload),
  );

  if (runbook.isPending) {
    return <EmptyState title="Loading runbook" description="Fetching runbook detail." />;
  }
  if (!runbook.data) {
    return <EmptyState title="Runbook unavailable" description="The runbook could not be loaded." />;
  }

  return (
    <section className="space-y-4">
      <div className="flex justify-end">
        <Button variant="outline" onClick={() => setEditing((value) => !value)}>
          {editing ? "Read" : "Edit"}
        </Button>
      </div>
      {editing ? (
        <RunbookEditor
          isSaving={save.isPending}
          runbook={runbook.data}
          staleVersion={staleVersion}
          onReload={() => {
            setStaleVersion(null);
            void runbook.refetch();
          }}
          onSubmit={(payload) =>
            save.mutate(payload, {
              onError: (error) => {
                const detail = (error as Error & { details?: { current_version?: number } }).details;
                setStaleVersion(detail?.current_version ?? runbook.data.version);
              },
            })
          }
        />
      ) : (
        <RunbookViewer runbook={runbook.data} />
      )}
    </section>
  );
}
