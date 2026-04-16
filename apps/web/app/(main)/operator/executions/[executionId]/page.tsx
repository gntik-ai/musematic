"use client";

import { ExecutionDrilldown } from "@/components/features/operator/ExecutionDrilldown";

interface OperatorExecutionDetailPageProps {
  params: {
    executionId: string;
  };
}

export default function OperatorExecutionDetailPage({
  params,
}: OperatorExecutionDetailPageProps) {
  return <ExecutionDrilldown executionId={params.executionId} />;
}
