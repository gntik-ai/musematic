"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef } from "react";
import { Plus, Workflow } from "lucide-react";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkflowList } from "@/lib/hooks/use-workflow-list";
import { useWorkspaceStore } from "@/store/workspace-store";
import { WorkflowCard } from "@/components/features/workflows/WorkflowCard";

function WorkflowCardSkeleton() {
  return (
    <div className="rounded-xl border border-border/60 bg-card/90 p-6 shadow-sm">
      <div className="space-y-3">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
      <div className="mt-6 grid gap-2 sm:grid-cols-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-32" />
      </div>
      <div className="mt-6 flex gap-3">
        <Skeleton className="h-9 w-28 rounded-md" />
        <Skeleton className="h-9 w-36 rounded-md" />
      </div>
    </div>
  );
}

export function WorkflowList() {
  const currentWorkspace = useWorkspaceStore((state) => state.currentWorkspace);
  const workspaceId = currentWorkspace?.id ?? null;
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const {
    data,
    isLoading,
    isFetchingNextPage,
    fetchNextPage,
    hasNextPage,
  } = useWorkflowList({ limit: 6 });

  const workflows = useMemo(
    () => data?.pages.flatMap((page) => page.items) ?? [],
    [data],
  );

  useEffect(() => {
    const node = loadMoreRef.current;
    if (!node || !hasNextPage || isFetchingNextPage) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void fetchNextPage();
        }
      },
      {
        rootMargin: "200px 0px",
      },
    );

    observer.observe(node);
    return () => {
      observer.disconnect();
    };
  }, [fetchNextPage, hasNextPage, isFetchingNextPage, workflows.length]);

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before browsing workflow definitions."
        icon={Workflow}
        title="Choose a workspace"
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Author, revise, and inspect workflow definitions for{" "}
            <span className="font-medium text-foreground">
              {currentWorkspace?.name ?? "this workspace"}
            </span>
            .
          </p>
        </div>
        <Button asChild className="shrink-0">
          <Link href="/workflow-editor-monitor/new">
            <Plus className="h-4 w-4" />
            New Workflow
          </Link>
        </Button>
      </div>

      {!isLoading && workflows.length === 0 ? (
        <EmptyState
          ctaLabel="Create workflow"
          description="No workflow definitions exist in this workspace yet."
          icon={Workflow}
          onCtaClick={() => {
            window.location.assign("/workflow-editor-monitor/new");
          }}
          title="No workflows yet"
        />
      ) : (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            {isLoading
              ? Array.from({ length: 4 }, (_, index) => (
                  <WorkflowCardSkeleton key={`workflow-skeleton-${index}`} />
                ))
              : workflows.map((workflow) => (
                  <WorkflowCard key={workflow.id} workflow={workflow} />
                ))}
          </div>

          {hasNextPage ? (
            <div
              aria-hidden="true"
              className="flex justify-center py-4"
              ref={loadMoreRef}
            >
              {isFetchingNextPage ? (
                <div className="grid w-full gap-4 xl:grid-cols-2">
                  <WorkflowCardSkeleton />
                  <WorkflowCardSkeleton />
                </div>
              ) : (
                <span className="text-sm text-muted-foreground">
                  Loading more workflows...
                </span>
              )}
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}
