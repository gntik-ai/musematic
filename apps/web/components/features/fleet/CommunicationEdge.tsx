"use client";

import {
  BaseEdge,
  type Edge,
  getSmoothStepPath,
  type EdgeProps,
} from "@xyflow/react";

interface CommunicationEdgeData extends Record<string, unknown> {
  relationship?: "communication" | "delegation" | "observation";
}

export function CommunicationEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps<Edge<CommunicationEdgeData>>) {
  const relationship = data?.relationship ?? "communication";
  const [path] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  const strokeDasharray =
    relationship === "delegation"
      ? "8 8"
      : relationship === "observation"
        ? "2 8"
        : undefined;

  const stroke =
    relationship === "observation"
      ? "hsl(var(--muted-foreground) / 0.55)"
      : relationship === "delegation"
        ? "hsl(var(--brand-accent))"
        : "hsl(var(--foreground) / 0.75)";

  return (
    <BaseEdge
      id={id}
      path={path}
      style={{
        stroke,
        strokeDasharray,
        strokeWidth: relationship === "communication" ? 2.2 : 1.8,
      }}
      {...(typeof markerEnd === "string" ? { markerEnd } : {})}
    />
  );
}
