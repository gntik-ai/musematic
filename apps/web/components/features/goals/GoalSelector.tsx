"use client";

import { Select } from "@/components/ui/select";
import { GoalLifecycleIndicator } from "@/components/features/goals/GoalLifecycleIndicator";
import { useConversationStore } from "@/lib/stores/conversation-store";
import type { WorkspaceGoal } from "@/types/conversations";

interface GoalSelectorProps {
  goals: WorkspaceGoal[];
  selectedGoalId: string | null;
}

export function GoalSelector({
  goals,
  selectedGoalId,
}: GoalSelectorProps) {
  const setSelectedGoal = useConversationStore((state) => state.setSelectedGoal);
  const selectedGoal =
    goals.find((goal) => goal.id === selectedGoalId) ?? goals[0] ?? null;

  return (
    <div className="min-w-0 space-y-2">
      <Select
        aria-label="Select goal"
        className="min-w-0"
        onChange={(event) => setSelectedGoal(event.target.value)}
        value={selectedGoal?.id ?? ""}
      >
        {goals.map((goal) => (
          <option key={goal.id} value={goal.id}>
            {goal.title}
          </option>
        ))}
      </Select>
      {selectedGoal ? <GoalLifecycleIndicator status={selectedGoal.status} /> : null}
    </div>
  );
}
