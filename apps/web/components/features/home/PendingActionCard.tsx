"use client";

import { useMemo } from "react";
import { formatDistanceToNow } from "date-fns";
import { AlertTriangle, ArrowRight, CheckCircle2, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { StatusBadge } from "@/components/shared/StatusBadge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "@/lib/hooks/use-toast";
import { ApiError } from "@/types/api";
import { useApproveMutation } from "@/lib/hooks/use-home-data";
import type { PendingAction } from "@/lib/types/home";
import { cn } from "@/lib/utils";

interface PendingActionCardProps {
  action: PendingAction;
  workspaceId: string;
}

const urgencyBorderClass = {
  high: "border-l-4 border-l-destructive",
  medium: "border-l-4 border-l-amber-500",
  low: "",
} as const;

const urgencyStatus = {
  high: "error",
  medium: "warning",
  low: "pending",
} as const;

const urgencyLabel = {
  high: "Critical",
  medium: "Warning",
  low: "Info",
} as const;

export function PendingActionCard({
  action,
  workspaceId,
}: PendingActionCardProps) {
  const router = useRouter();
  const mutation = useApproveMutation(workspaceId);

  const orderedActions = useMemo(
    () =>
      [...action.actions].sort((left, right) => {
        const leftPriority = left.action === "navigate" ? 1 : 0;
        const rightPriority = right.action === "navigate" ? 1 : 0;
        return leftPriority - rightPriority;
      }),
    [action.actions],
  );

  const handleAction = async (
    button: PendingAction["actions"][number],
  ): Promise<void> => {
    if (button.action === "navigate") {
      router.push(action.href);
      return;
    }

    if (!button.endpoint || !button.method) {
      return;
    }

    try {
      await mutation.mutateAsync({
        endpoint: button.endpoint,
        method: button.method,
      });
      toast({
        title: "Action completed",
        description: `${action.title} has been updated.`,
        variant: "success",
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        toast({
          title: "This action has already been resolved",
          variant: "destructive",
        });
        return;
      }

      if (error instanceof ApiError && error.status === 403) {
        toast({
          title: "You don't have permission to perform this action",
          variant: "destructive",
        });
        return;
      }

      toast({
        title: "Unable to update this action",
        description: error instanceof Error ? error.message : undefined,
        variant: "destructive",
      });
    }
  };

  return (
    <Card
      className={cn(
        "bg-card/90",
        urgencyBorderClass[action.urgency],
      )}
    >
      <CardHeader className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="text-base">{action.title}</CardTitle>
            <CardDescription>{action.description}</CardDescription>
          </div>
          <StatusBadge
            label={urgencyLabel[action.urgency]}
            status={urgencyStatus[action.urgency]}
          />
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <p className="text-sm text-muted-foreground">
          {formatDistanceToNow(new Date(action.created_at), { addSuffix: true })}
        </p>
      </CardContent>
      <CardFooter className="flex flex-wrap gap-2">
        {orderedActions.map((button) => {
          const isBusy =
            mutation.isPending &&
            button.action !== "navigate";

          return (
            <Button
              key={button.id}
              disabled={isBusy}
              onClick={() => {
                void handleAction(button);
              }}
              size="sm"
              variant={button.variant}
            >
              {isBusy ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : button.action === "approve" ? (
                <CheckCircle2 className="h-3.5 w-3.5" />
              ) : button.action === "reject" ? (
                <AlertTriangle className="h-3.5 w-3.5" />
              ) : (
                <ArrowRight className="h-3.5 w-3.5" />
              )}
              {button.label}
            </Button>
          );
        })}
      </CardFooter>
    </Card>
  );
}
