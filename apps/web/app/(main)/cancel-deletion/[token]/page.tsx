"use client";

import { useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { CheckCircle2, Loader2, ShieldAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useCancelWorkspaceDeletion } from "@/lib/hooks/use-data-lifecycle";

export default function CancelDeletionPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const cancelMutation = useCancelWorkspaceDeletion();
  const triggered = useRef(false);

  useEffect(() => {
    if (triggered.current) return;
    triggered.current = true;
    cancelMutation.mutate(params.token);
  }, [cancelMutation, params.token]);

  return (
    <div className="mx-auto max-w-md py-16">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {cancelMutation.isPending ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : cancelMutation.isError ? (
              <ShieldAlert className="h-5 w-5 text-destructive" />
            ) : (
              <CheckCircle2 className="h-5 w-5 text-emerald-500" />
            )}
            Cancel deletion
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {cancelMutation.isPending ? (
            <p>Validating cancellation token…</p>
          ) : null}
          {cancelMutation.isSuccess ? (
            <Alert>
              <AlertTitle>Deletion cancelled</AlertTitle>
              <AlertDescription>
                The workspace deletion has been aborted and the workspace is
                accessible again.
              </AlertDescription>
            </Alert>
          ) : null}
          {cancelMutation.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Cancellation failed</AlertTitle>
              <AlertDescription>
                {cancelMutation.error?.message ??
                  "The token is invalid, expired, or the grace period has ended."}
              </AlertDescription>
            </Alert>
          ) : null}
          <Button onClick={() => router.push("/home")} variant="outline">
            Return to dashboard
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
