"use client";

/**
 * UPD-049 — Marketplace review queue table.
 *
 * Renders rows from `useReviewQueue`. Each row is a Link to the
 * detail page at `/admin/marketplace-review/[agentId]`.
 */

import Link from "next/link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { ReviewSubmissionView } from "@/lib/marketplace/types";

export interface ReviewQueueTableProps {
  items: ReviewSubmissionView[];
}

function formatAge(minutes: number): string {
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

export function ReviewQueueTable({ items }: ReviewQueueTableProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-md border p-8 text-center text-muted-foreground">
        No pending submissions in the queue.
      </div>
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Agent</TableHead>
          <TableHead>Tenant</TableHead>
          <TableHead>Submitter</TableHead>
          <TableHead>Category</TableHead>
          <TableHead>Age</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => (
          <TableRow key={item.agent_id} data-testid={`review-row-${item.agent_id}`}>
            <TableCell>
              <Link
                href={`/admin/marketplace-review/${item.agent_id}`}
                className="font-medium hover:underline"
              >
                {item.agent_fqn}
              </Link>
            </TableCell>
            <TableCell>{item.tenant_slug}</TableCell>
            <TableCell>{item.submitter_email || item.submitter_user_id}</TableCell>
            <TableCell>
              <Badge variant="secondary">{item.category}</Badge>
            </TableCell>
            <TableCell>{formatAge(item.age_minutes)}</TableCell>
            <TableCell>
              {item.claimed_by_user_id ? (
                <Badge variant="outline">Claimed</Badge>
              ) : (
                <Badge>Unclaimed</Badge>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
