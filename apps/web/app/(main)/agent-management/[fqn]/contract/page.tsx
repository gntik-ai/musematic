"use client";

import { use, useMemo } from "react";
import { ContractEditor } from "./_components/ContractEditor";

export default function ContractPage({ params }: { params: Promise<{ fqn: string }> }) {
  const resolvedParams = use(params);
  const fqn = useMemo(() => decodeURIComponent(resolvedParams.fqn), [resolvedParams.fqn]);

  return <ContractEditor fqn={fqn} />;
}

