"use client";

import * as React from "react";
import { usePlatformStatus } from "@/lib/hooks/use-platform-status";
import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "secondary" | "outline" | "ghost" | "destructive";
type ButtonSize = "default" | "sm" | "lg" | "icon";
type MaintenanceDisabledConfig = boolean | { endsAt?: string | null };

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
  disabledByMaintenance?: MaintenanceDisabledConfig;
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantClasses: Record<ButtonVariant, string> = {
  default: "bg-primary text-primary-foreground hover:bg-primary/90 shadow-glow",
  secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
  outline: "border border-border bg-background hover:bg-accent hover:text-accent-foreground",
  ghost: "hover:bg-accent hover:text-accent-foreground",
  destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
};

const sizeClasses: Record<ButtonSize, string> = {
  default: "h-10 px-4 py-2",
  sm: "h-9 rounded-md px-3",
  lg: "h-11 rounded-md px-8",
  icon: "h-10 w-10",
};

type BaseButtonProps = Omit<ButtonProps, "disabledByMaintenance">;

const BaseButton = React.forwardRef<HTMLButtonElement, BaseButtonProps>(
  (
    {
      asChild = false,
      children,
      className,
      size = "default",
      variant = "default",
      type = "button",
      ...props
    },
    ref,
  ) => {
    const sharedClassName = cn(
      "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
      variantClasses[variant],
      sizeClasses[size],
      className,
    );

    if (asChild && React.isValidElement(children)) {
      return React.cloneElement(children as React.ReactElement<Record<string, unknown>>, {
        ...props,
        className: cn(sharedClassName, (children.props as { className?: string }).className),
      });
    }

    return (
      <button
        ref={ref}
        type={type}
        className={sharedClassName}
        {...props}
      >
        {children}
      </button>
    );
  },
);

BaseButton.displayName = "BaseButton";

function formatMaintenanceEnd(value?: string | null) {
  if (!value) {
    return "the maintenance window ends";
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const MaintenanceAwareButton = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ disabledByMaintenance, disabled, title, ...props }, ref) => {
    const { data } = usePlatformStatus();
    const maintenance = data?.active_maintenance;
    const configuredEndsAt =
      typeof disabledByMaintenance === "object" ? disabledByMaintenance.endsAt : undefined;
    const endsAt = configuredEndsAt ?? maintenance?.ends_at;
    const blocked = Boolean(disabledByMaintenance && maintenance?.blocks_writes);
    const message = `Writes are paused until ${formatMaintenanceEnd(endsAt)}.`;
    const descriptionId = React.useId();

    return (
      <span className="inline-flex">
        <BaseButton
          ref={ref}
          {...props}
          aria-describedby={blocked ? descriptionId : props["aria-describedby"]}
          disabled={disabled || blocked}
          title={blocked ? message : title}
        />
        {blocked ? (
          <span className="sr-only" id={descriptionId}>
            {message}
          </span>
        ) : null}
      </span>
    );
  },
);

MaintenanceAwareButton.displayName = "MaintenanceAwareButton";

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ disabledByMaintenance = false, ...props }, ref) => {
    if (disabledByMaintenance) {
      return (
        <MaintenanceAwareButton
          ref={ref}
          disabledByMaintenance={disabledByMaintenance}
          {...props}
        />
      );
    }

    return <BaseButton ref={ref} {...props} />;
  },
);

Button.displayName = "Button";
