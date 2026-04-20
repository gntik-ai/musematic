"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

type ToggleSize = "default" | "sm";

const sizeClasses: Record<ToggleSize, string> = {
  default: "h-10 px-4 py-2",
  sm: "h-8 px-3 text-xs",
};

export interface ToggleProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "onChange"> {
  pressed?: boolean;
  onPressedChange?: (pressed: boolean) => void;
  size?: ToggleSize;
}

export const Toggle = React.forwardRef<HTMLButtonElement, ToggleProps>(
  (
    {
      children,
      className,
      disabled,
      onClick,
      onPressedChange,
      pressed = false,
      size = "default",
      type = "button",
      ...props
    },
    ref,
  ) => (
    <button
      aria-pressed={pressed}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md border border-border bg-background font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
        pressed
          ? "bg-accent text-accent-foreground shadow-sm"
          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
        sizeClasses[size],
        className,
      )}
      data-state={pressed ? "on" : "off"}
      disabled={disabled}
      onClick={(event) => {
        onClick?.(event);
        if (!event.defaultPrevented && !disabled) {
          onPressedChange?.(!pressed);
        }
      }}
      ref={ref}
      type={type}
      {...props}
    >
      {children}
    </button>
  ),
);

Toggle.displayName = "Toggle";
