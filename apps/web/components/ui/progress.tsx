import { cn } from "@/lib/utils";

interface ProgressProps {
  "aria-label"?: string;
  className?: string;
  indicatorClassName?: string;
  value: number;
}

export function Progress({
  "aria-label": ariaLabel = "Progress",
  className,
  indicatorClassName,
  value,
}: ProgressProps) {
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={Math.round(clamped)}
      aria-label={ariaLabel}
      className={cn("h-2.5 w-full overflow-hidden rounded-full bg-muted", className)}
      role="progressbar"
    >
      <div
        className={cn(
          "h-full rounded-full bg-primary transition-[width] duration-300",
          indicatorClassName,
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
