import { GitBranch } from "lucide-react";

export function BranchOriginIndicator() {
  return (
    <span
      aria-label="Has branches"
      className="inline-flex items-center gap-1 text-xs text-muted-foreground"
    >
      <GitBranch className="h-3.5 w-3.5" />
      branched
    </span>
  );
}
