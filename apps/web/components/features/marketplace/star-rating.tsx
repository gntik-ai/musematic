"use client";

import { Star } from "lucide-react";
import { cn } from "@/lib/utils";

export interface StarRatingProps {
  rating: number | null;
  reviewCount?: number;
  size?: "sm" | "md" | "lg";
}

const sizeClasses = {
  sm: "h-3.5 w-3.5",
  md: "h-4 w-4",
  lg: "h-5 w-5",
} as const;

export function StarRating({
  rating,
  reviewCount,
  size = "md",
}: StarRatingProps) {
  if (rating === null) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>No ratings</span>
        {typeof reviewCount === "number" ? <span>({reviewCount})</span> : null}
      </div>
    );
  }

  const rounded = Math.round(rating);

  return (
    <div className="flex items-center gap-2 text-sm">
      <div className="flex items-center gap-1">
        {Array.from({ length: 5 }, (_, index) => (
          <Star
            key={index}
            aria-hidden="true"
            className={cn(
              sizeClasses[size],
              index < rounded
                ? "fill-current text-yellow-400 dark:text-yellow-300"
                : "text-muted-foreground/40",
            )}
          />
        ))}
      </div>
      <span className="font-medium">{rating.toFixed(1)}</span>
      {typeof reviewCount === "number" ? (
        <span className="text-muted-foreground">({reviewCount} reviews)</span>
      ) : null}
    </div>
  );
}
