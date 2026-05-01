"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_STATUS_API_URL ?? "";

export function TokenActionClient({
  endpoint,
  title,
}: {
  endpoint: "confirm" | "unsubscribe";
  title: string;
}) {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"loading" | "success" | "invalid">("loading");

  useEffect(() => {
    if (!token) {
      setState("invalid");
      return;
    }
    let mounted = true;
    void fetch(
      `${API_BASE}/api/v1/public/subscribe/email/${endpoint}?${new URLSearchParams({ token })}`,
    ).then((response) => {
      if (mounted) {
        setState(response.ok ? "success" : "invalid");
      }
    });
    return () => {
      mounted = false;
    };
  }, [endpoint, token]);

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto grid w-full max-w-2xl gap-4 px-4 py-10">
        <h1 className="text-2xl font-semibold">{title}</h1>
        {state === "loading" ? <p className="text-muted-foreground">Checking token...</p> : null}
        {state === "success" ? (
          <p className="rounded-md border border-emerald-200 bg-emerald-50 p-4 text-emerald-950">
            Request completed.
          </p>
        ) : null}
        {state === "invalid" ? (
          <p className="rounded-md border border-red-200 bg-red-50 p-4 text-red-950">
            This link is invalid or expired.
          </p>
        ) : null}
      </div>
    </main>
  );
}
