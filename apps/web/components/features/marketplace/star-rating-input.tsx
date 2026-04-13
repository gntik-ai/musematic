"use client";

import { Star } from "lucide-react";
import { cn } from "@/lib/utils";

export interface StarRatingInputProps {
  value: number;
  onChange: (rating: number) => void;
  disabled?: boolean;
  name: string;
}

export function StarRatingInput({
  value,
  onChange,
  disabled = false,
  name,
}: StarRatingInputProps) {
  return (
    <div
      aria-label={name}
      className="flex items-center gap-1"
      role="radiogroup"
      onKeyDown={(event) => {
        if (disabled) {
          return;
        }

        if (event.key === "ArrowRight" || event.key === "ArrowUp") {
          event.preventDefault();
          onChange(Math.min(5, value + 1));
        }

        if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
          event.preventDefault();
          onChange(Math.max(1, value - 1));
        }

        if (event.key === "Home") {
          event.preventDefault();
          onChange(1);
        }

        if (event.key === "End") {
          event.preventDefault();
          onChange(5);
        }
      }}
    >
      {Array.from({ length: 5 }, (_, index) => {
        const rating = index + 1;
        const selected = rating <= value;

        return (
          <button
            key={rating}
            aria-current={rating === value ? "true" : undefined}
            aria-label={`Rate ${rating} out of 5 stars`}
            className="rounded-md p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            disabled={disabled}
            type="button"
            onClick={() => onChange(rating)}
          >
            <Star
              className={cn(
                "h-5 w-5",
                selected
                  ? "fill-current text-yellow-400 dark:text-yellow-300"
                  : "text-muted-foreground/40",
              )}
            />
          </button>
        );
      })}
    </div>
  );
}
