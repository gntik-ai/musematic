import * as React from "react";
import { cn } from "@/lib/utils";

export interface SwitchProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "onChange"> {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
}

export const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  (
    {
      checked = false,
      className,
      disabled = false,
      onCheckedChange,
      type = "button",
      ...props
    },
    ref,
  ) => {
    return (
      <button
        ref={ref}
        aria-checked={checked}
        className={cn(
          "peer inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-transparent",
          "transition-colors focus-visible:outline-none focus-visible:ring-2",
          "focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
          checked ? "bg-primary justify-end" : "bg-muted justify-start",
          className,
        )}
        disabled={disabled}
        role="switch"
        type={type}
        onClick={(event) => {
          props.onClick?.(event);
          if (!event.defaultPrevented && !disabled) {
            onCheckedChange?.(!checked);
          }
        }}
        {...props}
      >
        <span className="mx-0.5 h-5 w-5 rounded-full bg-background shadow-sm transition-transform" />
      </button>
    );
  },
);

Switch.displayName = "Switch";
