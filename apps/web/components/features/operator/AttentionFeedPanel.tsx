"use client";

import { useRouter } from "next/navigation";
import { BellDot } from "lucide-react";
import { AttentionFeedItem } from "@/components/features/operator/AttentionFeedItem";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAttentionFeed } from "@/lib/hooks/use-attention-feed";
import { useAttentionFeedStore } from "@/lib/stores/use-attention-feed-store";
import { getAttentionTargetHref } from "@/lib/types/operator-dashboard";
import { useAuthStore } from "@/store/auth-store";
import { cn } from "@/lib/utils";

export interface AttentionFeedPanelProps {
  className?: string;
}

export function AttentionFeedPanel({ className }: AttentionFeedPanelProps) {
  const router = useRouter();
  const userId = useAuthStore((state) => state.user?.id ?? null);
  const { isLoading } = useAttentionFeed(userId);
  const events = useAttentionFeedStore((state) => state.events);
  const pendingEvents = events.filter((event) => event.status === "pending");

  return (
    <Card className={cn("rounded-[1.75rem]", className)}>
      <CardHeader className="flex flex-row items-center justify-between gap-4">
        <div>
          <CardTitle>Agent attention</CardTitle>
          <p className="text-sm text-muted-foreground">
            Pending escalation requests from live agent workflows.
          </p>
        </div>
        <Badge variant="outline">{pendingEvents.length} pending</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-24 rounded-xl" />
          ))
        ) : pendingEvents.length === 0 ? (
          <EmptyState
            description="No pending attention requests"
            icon={BellDot}
            title="Attention queue clear"
          />
        ) : (
          pendingEvents.map((event) => (
            <AttentionFeedItem
              key={event.id}
              event={event}
              onClick={(item) => {
                const href = getAttentionTargetHref(item);
                if (!href) {
                  return;
                }

                router.push(href);
              }}
            />
          ))
        )}
      </CardContent>
    </Card>
  );
}
