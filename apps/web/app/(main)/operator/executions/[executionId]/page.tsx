"use client";

import { use } from "react";
import { ExecutionDrilldown } from "@/components/features/operator/ExecutionDrilldown";

interface OperatorExecutionDetailPageProps {
  params: Promise<{
    executionId: string;
  }>;
}

export default function OperatorExecutionDetailPage({
  params,
}: OperatorExecutionDetailPageProps) {
  const { executionId } = use(params);

  return <ExecutionDrilldown executionId={executionId} />;
}
