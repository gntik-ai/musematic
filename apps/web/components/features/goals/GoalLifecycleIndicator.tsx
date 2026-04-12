import { Badge } from "@/components/ui/badge";
import type { GoalStatus } from "@/types/conversations";

function getGoalVariant(status: GoalStatus) {
  switch (status) {
    case "completed":
      return "secondary";
    case "abandoned":
      return "destructive";
    case "paused":
      return "outline";
    default:
      return "default";
  }
}

export function GoalLifecycleIndicator({ status }: { status: GoalStatus }) {
  return (
    <Badge
      aria-label={`Goal status: ${status}`}
      variant={getGoalVariant(status)}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  );
}
