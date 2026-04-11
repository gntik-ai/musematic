"use client";

import { AlertTriangle, CheckCircle2, Clock, Loader2, MinusCircle, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn, toTitleCase } from "@/lib/utils";

export type StatusSemantic = "healthy" | "warning" | "error" | "inactive" | "pending" | "running";

export interface StatusBadgeProps {
  status: StatusSemantic;
  label?: string;
  size?: "sm" | "md" | "lg";
  showIcon?: boolean;
}

const config = {
  healthy: { variant: "default", icon: CheckCircle2, className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300" },
  warning: { variant: "secondary", icon: AlertTriangle, className: "bg-amber-500/15 text-amber-700 dark:text-amber-300" },
  error: { variant: "destructive", icon: XCircle, className: "" },
  inactive: { variant: "outline", icon: MinusCircle, className: "text-muted-foreground" },
  pending: { variant: "outline", icon: Clock, className: "text-foreground" },
  running: { variant: "default", icon: Loader2, className: "bg-brand-primary/15 text-brand-primary" },
} as const;

const sizeClasses = {
  sm: "text-xs",
  md: "text-sm",
  lg: "text-base",
} as const;

export function StatusBadge({
  status,
  label,
  showIcon = true,
  size = "md",
}: StatusBadgeProps) {
  const Icon = config[status].icon;

  return (
    <Badge
      aria-label={`status ${label ?? status}`}
      className={cn("gap-1.5 border-transparent", sizeClasses[size], config[status].className)}
      variant={config[status].variant}
    >
      {showIcon ? <Icon className={cn("h-3.5 w-3.5", status === "running" && "animate-spin")} /> : null}
      {label ?? toTitleCase(status)}
    </Badge>
  );
}
