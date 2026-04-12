"use client";

import { Target } from "lucide-react";
import { ConnectionStatusBanner } from "@/components/features/home/ConnectionStatusBanner";
import { GoalFeed } from "@/components/features/goals/GoalFeed";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { useGoalWs } from "@/lib/hooks/use-goal-ws";
import { useWebSocketStatus } from "@/lib/hooks/use-home-data";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function ConversationsLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const goalPanelOpen = useConversationStore((state) => state.goalPanelOpen);
  const selectedGoalId = useConversationStore((state) => state.selectedGoalId);
  const setGoalPanelOpen = useConversationStore((state) => state.setGoalPanelOpen);
  const currentWorkspace = useWorkspaceStore((state) => state.currentWorkspace);
  const userWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspace?.id ?? userWorkspaceId;
  const { isConnected } = useWebSocketStatus();

  useGoalWs(workspaceId);

  return (
    <div className="flex min-h-full flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-brand-accent">
            Conversations
          </p>
          <h1 className="mt-2 text-3xl font-semibold">Conversation workspace</h1>
        </div>
        <Sheet open={goalPanelOpen} onOpenChange={setGoalPanelOpen}>
          <SheetTrigger asChild>
            <Button aria-label="Open goal feed" variant="outline">
              <Target className="h-4 w-4" />
              Goal feed
            </Button>
          </SheetTrigger>
          <SheetContent className="ml-auto flex h-full max-w-xl flex-col">
            <SheetTitle>Workspace goals</SheetTitle>
            <SheetDescription>
              Goal activity stays synchronized with the active workspace.
            </SheetDescription>
            {workspaceId ? (
              <div className="mt-6 min-h-0 flex-1">
                <GoalFeed
                  className="h-full"
                  initialGoalId={selectedGoalId}
                  workspaceId={workspaceId}
                />
              </div>
            ) : (
              <div className="mt-6 rounded-2xl border border-dashed border-border bg-muted/20 p-6 text-sm text-muted-foreground">
                Select a workspace to load goal activity.
              </div>
            )}
          </SheetContent>
        </Sheet>
      </div>
      <ConnectionStatusBanner isConnected={isConnected} />
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
