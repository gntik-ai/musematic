"use client";

import { registerClientErrorHandlers } from "@/instrumentation";
import { useEffect } from "react";

export function ClientErrorLogging() {
  useEffect(() => registerClientErrorHandlers(), []);
  return null;
}
