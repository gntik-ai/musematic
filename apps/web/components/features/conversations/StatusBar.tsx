import { Badge } from "@/components/ui/badge";
import { formatReasoningMode, type Interaction } from "@/types/conversations";

interface StatusBarProps {
  interaction: Interaction;
  isProcessing: boolean;
}

function getStateVariant(interaction: Interaction) {
  switch (interaction.state) {
    case "completed":
      return "secondary";
    case "failed":
      return "destructive";
    case "awaiting_approval":
      return "outline";
    default:
      return "default";
  }
}

function formatStateLabel(state: Interaction["state"]) {
  return state
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function StatusBar({
  interaction,
  isProcessing,
}: StatusBarProps) {
  const stateVariant = getStateVariant(interaction);

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-border bg-card px-4 py-3">
      <Badge
        className={interaction.state === "awaiting_approval" ? "animate-pulse" : undefined}
        variant={stateVariant}
      >
        {formatStateLabel(interaction.state)}
      </Badge>
      <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
        {interaction.agent_fqn}
      </span>
      <span className="min-w-0 truncate text-sm text-muted-foreground">
        {formatReasoningMode(interaction.reasoning_mode)}
      </span>
      {interaction.self_correction_count > 0 ? (
        <span className="min-w-0 truncate text-sm text-muted-foreground">
          {interaction.self_correction_count} corrections
        </span>
      ) : null}
      {isProcessing ? (
        <span className="rounded-full bg-yellow-500/10 px-2 py-1 text-xs text-yellow-700 dark:text-yellow-300">
          Processing
        </span>
      ) : null}
    </div>
  );
}
