"use client";

/**
 * UPD-049 refresh (102) — Reviewer assignment controls for the review-queue
 * detail page. Renders Assign / Unassign actions; the assign target picker
 * filters out the submitter so a lead cannot accidentally assign a
 * submission to its own author (FR-741.9 — defense in depth; the backend
 * also refuses).
 */

import { useState } from "react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  useAssignReviewer,
  useUnassignReviewer,
} from "@/lib/hooks/use-marketplace-review";

export interface ReviewQueueAssignmentControlsProps {
  agentId: string;
  submitterUserId: string;
  assignedReviewerUserId: string | null | undefined;
  assignedReviewerEmail: string | null | undefined;
}

export function ReviewQueueAssignmentControls({
  agentId,
  submitterUserId,
  assignedReviewerUserId,
  assignedReviewerEmail,
}: ReviewQueueAssignmentControlsProps) {
  const assign = useAssignReviewer();
  const unassign = useUnassignReviewer();
  const [open, setOpen] = useState(false);
  const [reviewerInput, setReviewerInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Defensive client-side check — server enforces FR-741.9 too.
  const isSelfAssignment = reviewerInput.trim() === submitterUserId;

  const onSubmit = async () => {
    const value = reviewerInput.trim();
    if (!value) {
      setError("Reviewer user id is required.");
      return;
    }
    if (value === submitterUserId) {
      setError("You cannot assign a submission to its author.");
      return;
    }
    try {
      await assign.mutateAsync({
        agentId,
        body: { reviewer_user_id: value },
      });
      setOpen(false);
      setReviewerInput("");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Assign failed");
    }
  };

  const onUnassign = async () => {
    try {
      await unassign.mutateAsync(agentId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unassign failed");
    }
  };

  return (
    <Card data-testid="review-assignment-card">
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Assignment</CardTitle>
        {assignedReviewerUserId ? (
          <Badge variant="outline" data-testid="assigned-badge">
            {assignedReviewerEmail ?? assignedReviewerUserId}
          </Badge>
        ) : (
          <Badge>Unassigned</Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        <Button
          variant="default"
          onClick={() => {
            setError(null);
            setOpen(true);
          }}
          disabled={assign.isPending}
          data-testid="assign-reviewer-button"
        >
          {assignedReviewerUserId ? "Reassign reviewer…" : "Assign reviewer…"}
        </Button>
        {assignedReviewerUserId ? (
          <Button
            variant="ghost"
            onClick={onUnassign}
            disabled={unassign.isPending}
            data-testid="unassign-reviewer-button"
          >
            Unassign
          </Button>
        ) : null}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign reviewer</DialogTitle>
            <DialogDescription>
              The selected reviewer will be exclusively allowed to claim
              and act on this submission. Reviewers cannot be the
              submitter.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="reviewer-user-id">Reviewer user id (UUID)</Label>
            <Input
              id="reviewer-user-id"
              data-testid="assign-reviewer-input"
              value={reviewerInput}
              onChange={(event) => {
                setReviewerInput(event.target.value);
                setError(null);
              }}
              placeholder="00000000-0000-0000-0000-000000000000"
            />
            {error ? (
              <p className="text-sm text-destructive" data-testid="assign-error">
                {error}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="default"
              onClick={onSubmit}
              disabled={
                assign.isPending || !reviewerInput.trim() || isSelfAssignment
              }
              data-testid="assign-reviewer-submit"
            >
              Assign
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
