import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { TenantStatus } from "@/lib/hooks/use-admin-tenants";

const statusLabels: Record<TenantStatus, string> = {
  active: "Active",
  suspended: "Suspended",
  pending_deletion: "Pending deletion",
};

const statusClasses: Record<TenantStatus, string> = {
  active: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  suspended: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  pending_deletion: "border-destructive/30 bg-destructive/10 text-destructive",
};

export function TenantStatusBadge({ status }: { status: TenantStatus }) {
  return (
    <Badge
      variant="outline"
      className={cn("rounded-md whitespace-nowrap", statusClasses[status])}
    >
      {statusLabels[status]}
    </Badge>
  );
}
