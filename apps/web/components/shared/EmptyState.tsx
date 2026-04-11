import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

export function EmptyState({
  title,
  description,
  ctaLabel,
  onCtaClick,
  icon: Icon,
}: {
  title: string;
  description: string;
  ctaLabel?: string;
  onCtaClick?: () => void;
  icon?: LucideIcon;
}) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-muted/30 px-6 py-10 text-center">
      {Icon ? <Icon className="mb-4 h-8 w-8 text-brand-accent" /> : null}
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">{description}</p>
      {ctaLabel && onCtaClick ? (
        <Button className="mt-5" onClick={onCtaClick} variant="secondary">
          {ctaLabel}
        </Button>
      ) : null}
    </div>
  );
}
