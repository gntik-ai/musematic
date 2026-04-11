import type * as React from "react";

export function TooltipProvider({ children }: React.PropsWithChildren) {
  return <>{children}</>;
}

export function Tooltip({ children }: React.PropsWithChildren) {
  return <>{children}</>;
}

export function TooltipTrigger({ children }: React.PropsWithChildren) {
  return <>{children}</>;
}

export function TooltipContent({ children }: React.PropsWithChildren) {
  return <span className="sr-only">{children}</span>;
}
