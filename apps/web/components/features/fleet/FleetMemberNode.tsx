"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Badge } from "@/components/ui/badge";
import type { FleetGraphNodeData } from "@/lib/utils/fleet-topology-layout";
import { getFleetHealthTone } from "@/lib/types/fleet";
import { cn } from "@/lib/utils";

export function FleetMemberNode({ data }: NodeProps<Node<FleetGraphNodeData>>) {
  const member = data.member;
  const tone = getFleetHealthTone(data.health_pct);
  const borderClassName =
    tone === "healthy"
      ? "border-emerald-500/70"
      : tone === "warning"
        ? "border-amber-500/70"
        : "border-rose-500/70";

  if (!member) {
    return null;
  }

  return (
    <div
      className={cn(
        "rounded-[1.5rem] border bg-card/95 p-4 shadow-lg transition-transform",
        borderClassName,
        data.selected && "scale-[1.04] shadow-xl",
      )}
    >
      <Handle className="opacity-0" position={Position.Top} type="target" />
      <Handle className="opacity-0" position={Position.Bottom} type="source" />
      <Handle className="opacity-0" position={Position.Left} type="target" />
      <Handle className="opacity-0" position={Position.Right} type="source" />
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <p className="text-sm font-semibold">{member.agent_name}</p>
            <p className="text-xs text-muted-foreground">{member.agent_fqn}</p>
          </div>
          <Badge className="capitalize" variant="outline">
            {member.role}
          </Badge>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">{member.availability}</span>
          <span className="font-medium">{Math.round(data.health_pct)}%</span>
        </div>
      </div>
    </div>
  );
}
