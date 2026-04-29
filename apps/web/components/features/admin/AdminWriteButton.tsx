"use client";

import type { ButtonProps } from "@/components/ui/button";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAdminStore } from "@/lib/stores/admin-store";

const READ_ONLY_TOOLTIP = "Disabled - this session is in read-only mode";

export function AdminWriteButton({
  children,
  disabled,
  title,
  ...props
}: ButtonProps) {
  const readOnlyMode = useAdminStore((state) => state.readOnlyMode);
  const isDisabled = disabled || readOnlyMode;
  const tooltip = readOnlyMode ? READ_ONLY_TOOLTIP : title;

  const button = (
    <Button
      {...props}
      disabled={isDisabled}
      title={tooltip}
      aria-disabled={isDisabled}
    >
      {children}
    </Button>
  );

  if (!readOnlyMode) {
    return button;
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>{button}</TooltipTrigger>
        <TooltipContent>{READ_ONLY_TOOLTIP}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
