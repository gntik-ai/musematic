import { CheckCircle2, CircleAlert, Info } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastVariant = "default" | "destructive" | "success";

const variantStyles: Record<ToastVariant, string> = {
  default: "border-border bg-card text-card-foreground",
  destructive: "border-destructive/30 bg-destructive/10 text-foreground",
  success: "border-emerald-500/30 bg-emerald-500/10 text-foreground",
};

const variantIcons = {
  default: Info,
  destructive: CircleAlert,
  success: CheckCircle2,
} satisfies Record<ToastVariant, typeof Info>;

export interface ToastProps {
  title: string;
  description?: string;
  variant?: ToastVariant;
}

export function Toast({ description, title, variant = "default" }: ToastProps) {
  const Icon = variantIcons[variant];

  return (
    <div
      className={cn(
        "flex w-full items-start gap-3 rounded-xl border p-4 shadow-lg backdrop-blur",
        variantStyles[variant],
      )}
      role="status"
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0">
        <p className="text-sm font-semibold">{title}</p>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
    </div>
  );
}
