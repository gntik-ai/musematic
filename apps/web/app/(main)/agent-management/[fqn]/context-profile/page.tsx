"use client";

import { use, useMemo } from "react";
import { ContextProfileEditor } from "./_components/ContextProfileEditor";

export default function ContextProfilePage({ params }: { params: Promise<{ fqn: string }> }) {
  const resolvedParams = use(params);
  const fqn = useMemo(() => decodeURIComponent(resolvedParams.fqn), [resolvedParams.fqn]);

  return <ContextProfileEditor fqn={fqn} />;
}

