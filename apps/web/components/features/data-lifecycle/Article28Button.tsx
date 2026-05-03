"use client";

import { useState } from "react";
import { FileCheck2, Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useGenerateArticle28Evidence } from "@/lib/hooks/use-data-lifecycle";

export function Article28Button({ tenantId }: { tenantId: string }) {
  const generate = useGenerateArticle28Evidence(tenantId);
  const [jobId, setJobId] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      <Button
        variant="outline"
        onClick={() =>
          generate.mutate(undefined, {
            onSuccess: (res) => setJobId(res.job_id),
          })
        }
        disabled={generate.isPending}
      >
        {generate.isPending ? (
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        ) : (
          <FileCheck2 className="mr-2 h-4 w-4" />
        )}
        Generate Article 28 evidence
      </Button>
      {jobId ? (
        <Alert>
          <AlertTitle>Generation in progress</AlertTitle>
          <AlertDescription className="text-xs">
            Job <span className="font-mono">{jobId}</span> dispatched. The
            evidence package will be available for download once the worker
            assembles the audit chain bundle.
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
