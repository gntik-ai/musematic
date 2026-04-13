"use client";

import { GripVertical } from "lucide-react";
import {
  Group,
  Panel,
  Separator,
  type GroupProps,
  type PanelProps,
  type SeparatorProps,
} from "react-resizable-panels";
import { cn } from "@/lib/utils";

export function ResizablePanelGroup({
  className,
  ...props
}: GroupProps) {
  return (
    <Group
      className={cn(
        "flex h-full w-full data-[panel-group-orientation=vertical]:flex-col",
        className,
      )}
      {...props}
    />
  );
}

export function ResizablePanel(props: PanelProps) {
  return <Panel {...props} />;
}

export function ResizableHandle({
  className,
  children,
  ...props
}: SeparatorProps) {
  return (
    <Separator
      className={cn(
        "group relative flex w-px items-center justify-center bg-border/80 transition-colors hover:bg-border",
        "data-[panel-group-orientation=vertical]:h-px data-[panel-group-orientation=vertical]:w-full",
        className,
      )}
      {...props}
    >
      {children ?? (
        <div className="flex h-10 w-5 items-center justify-center rounded-full border border-border/80 bg-background/95 text-muted-foreground shadow-sm transition-colors group-hover:text-foreground data-[panel-group-orientation=vertical]:h-5 data-[panel-group-orientation=vertical]:w-10">
          <GripVertical className="h-4 w-4" />
        </div>
      )}
    </Separator>
  );
}
