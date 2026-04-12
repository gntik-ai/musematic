"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { GoalMessageBubble } from "@/components/features/goals/GoalMessageBubble";
import { GoalSelector } from "@/components/features/goals/GoalSelector";
import {
  canPostToGoal,
  getSelectedGoal,
  useGoalMessages,
  useGoals,
  usePostGoalMessage,
} from "@/lib/hooks/use-workspace-goals";
import { useConversationStore } from "@/lib/stores/conversation-store";

interface GoalFeedProps {
  workspaceId: string;
  initialGoalId?: string | null;
  className?: string;
}

export function GoalFeed({
  workspaceId,
  initialGoalId = null,
  className,
}: GoalFeedProps) {
  const goalPanelOpen = useConversationStore((state) => state.goalPanelOpen);
  const selectedGoalId = useConversationStore((state) => state.selectedGoalId);
  const setSelectedGoal = useConversationStore((state) => state.setSelectedGoal);
  const [content, setContent] = useState("");
  const goalsQuery = useGoals(workspaceId);
  const goals = goalsQuery.data?.items ?? [];
  const selectedGoal = useMemo(
    () => getSelectedGoal(goals, selectedGoalId ?? initialGoalId),
    [goals, initialGoalId, selectedGoalId],
  );
  const messagesQuery = useGoalMessages(workspaceId, selectedGoal?.id ?? null);
  const postGoalMessage = usePostGoalMessage();
  const parentRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!selectedGoalId && initialGoalId) {
      setSelectedGoal(initialGoalId);
      return;
    }

    if (!selectedGoalId && goals[0]) {
      setSelectedGoal(goals[0].id);
    }
  }, [goals, initialGoalId, selectedGoalId, setSelectedGoal]);

  const rowVirtualizer = useVirtualizer({
    count: messagesQuery.messages.length,
    estimateSize: () => 96,
    getScrollElement: () => parentRef.current,
    overscan: 6,
  });

  const postingDisabled = !canPostToGoal(selectedGoal);

  return (
    <div className={`flex min-h-0 flex-1 flex-col gap-4 ${className ?? ""}`}>
      <GoalSelector
        goals={goals}
        selectedGoalId={selectedGoal?.id ?? null}
      />
      <div className="min-h-0 flex-1 overflow-auto" ref={(node) => {
        parentRef.current = node;
      }}>
        <div
          className="relative w-full"
          style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
        >
          {rowVirtualizer.getVirtualItems().map((virtualItem) => {
            const message = messagesQuery.messages[virtualItem.index];
            if (!message) {
              return null;
            }

            return (
              <div
                key={virtualItem.key}
                ref={rowVirtualizer.measureElement}
                style={{
                  position: "absolute",
                  top: 0,
                  transform: `translateY(${virtualItem.start}px)`,
                  width: "100%",
                }}
              >
                <div className="pb-4">
                  <GoalMessageBubble message={message} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="space-y-2 border-t border-border pt-4">
        <Textarea
          disabled={postingDisabled}
          onChange={(event) => setContent(event.target.value)}
          placeholder={
            selectedGoal && postingDisabled
              ? `This goal has been ${selectedGoal.status}`
              : "Add guidance to this goal…"
          }
          value={content}
        />
        <div className="flex justify-end">
          <Button
            disabled={postingDisabled || !content.trim()}
            onClick={async () => {
              if (!selectedGoal) {
                return;
              }

              await postGoalMessage.mutateAsync({
                content: content.trim(),
                goalId: selectedGoal.id,
                workspaceId,
              });
              setContent("");
            }}
          >
            Send
          </Button>
        </div>
        {!goalPanelOpen && selectedGoal ? (
          <p className="text-xs text-muted-foreground">
            Goal panel updates continue in the background.
          </p>
        ) : null}
      </div>
    </div>
  );
}
