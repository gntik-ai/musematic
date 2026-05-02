"use client";

/**
 * UPD-049 — Submission detail with claim / release / approve / reject
 * actions. The reject action requires a reason (FR-017).
 */

import { useMemo, useState } from "react";
import { useReviewQueue } from "@/lib/hooks/use-marketplace-review";
import {
  useApproveReview,
  useClaimReview,
  useRejectReview,
  useReleaseReview,
} from "@/lib/hooks/use-marketplace-review";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

interface ReviewSubmissionDetailProps {
  agentId: string;
}

export function ReviewSubmissionDetail({ agentId }: ReviewSubmissionDetailProps) {
  // The contract has no GET /{agent_id} detail endpoint yet — the queue
  // already carries everything the reviewer needs. We pull the current
  // queue and locate the row by agentId. If the row isn't in the queue
  // (stale link, already resolved), we fall back to a "not found" state.
  const { data, isLoading } = useReviewQueue();
  const submission = useMemo(
    () => data?.items.find((item) => item.agent_id === agentId),
    [data, agentId],
  );

  const claim = useClaimReview();
  const release = useReleaseReview();
  const approve = useApproveReview();
  const reject = useRejectReview();

  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-10 w-1/3" />
      </div>
    );
  }
  if (!submission) {
    return (
      <div className="rounded-md border p-8 text-center text-muted-foreground">
        Submission not found in the queue. It may have been resolved by another reviewer.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="space-y-1">
          <div className="flex items-center justify-between">
            <CardTitle className="font-mono text-xl">{submission.agent_fqn}</CardTitle>
            {submission.claimed_by_user_id ? (
              <Badge variant="outline">Claimed</Badge>
            ) : (
              <Badge>Unclaimed</Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            Submitted by {submission.submitter_email || submission.submitter_user_id}
            {" — "}
            {submission.tenant_slug}
            {" — "}
            {submission.age_minutes}m ago
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <section>
            <h3 className="text-sm font-medium">Marketing description</h3>
            <p className="mt-1 whitespace-pre-wrap text-sm">
              {submission.marketing_description}
            </p>
          </section>
          <section>
            <h3 className="text-sm font-medium">Category</h3>
            <Badge variant="secondary" className="mt-1">
              {submission.category}
            </Badge>
          </section>
          <section>
            <h3 className="text-sm font-medium">Tags</h3>
            <div className="mt-1 flex flex-wrap gap-2">
              {submission.tags.map((tag) => (
                <Badge key={tag} variant="outline">
                  {tag}
                </Badge>
              ))}
            </div>
          </section>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          onClick={() => claim.mutate(submission.agent_id)}
          disabled={claim.isPending}
        >
          Claim
        </Button>
        <Button
          variant="ghost"
          onClick={() => release.mutate(submission.agent_id)}
          disabled={release.isPending || !submission.claimed_by_user_id}
        >
          Release
        </Button>
        <Button
          variant="default"
          onClick={() =>
            approve.mutate({
              agentId: submission.agent_id,
              body: { notes: null },
            })
          }
          disabled={approve.isPending}
        >
          Approve
        </Button>
        <Button
          variant="destructive"
          onClick={() => setRejectOpen(true)}
          disabled={reject.isPending}
        >
          Reject…
        </Button>
      </div>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject submission</DialogTitle>
            <DialogDescription>
              The submitter is notified with the reason you provide here.
              The reason is required.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            rows={4}
            value={rejectReason}
            onChange={(event) => setRejectReason(event.target.value)}
            placeholder="Explain what needs to change before the agent can be approved."
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRejectOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={!rejectReason.trim() || reject.isPending}
              onClick={async () => {
                await reject.mutateAsync({
                  agentId: submission.agent_id,
                  body: { reason: rejectReason.trim() },
                });
                setRejectOpen(false);
                setRejectReason("");
              }}
            >
              Reject submission
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
