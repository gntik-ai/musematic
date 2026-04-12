import { Badge } from "@/components/ui/badge";

export function MidProcessBadge() {
  return (
    <Badge
      className="bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
      variant="outline"
    >
      sent during processing
    </Badge>
  );
}
