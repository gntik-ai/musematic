import { Badge } from "@/components/ui/badge";

export function MergedFromBadge({ branchName }: { branchName: string }) {
  return (
    <Badge
      className="bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200"
      variant="outline"
    >
      from: {branchName}
    </Badge>
  );
}
