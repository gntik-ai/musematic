"use client";

import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";

interface EmbeddedGrafanaPanelProps {
  path: string;
  title: string;
}

export function EmbeddedGrafanaPanel({ path, title }: EmbeddedGrafanaPanelProps) {
  const src = `/api/admin/grafana-proxy/${path.replace(/^\/+/, "")}`;

  return (
    <div className="overflow-hidden rounded-md border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <h2 className="text-sm font-medium">{title}</h2>
        <Button variant="ghost" size="sm" asChild>
          <a href={src} target="_blank" rel="noreferrer">
            <ExternalLink className="h-4 w-4" />
            Open
          </a>
        </Button>
      </div>
      <iframe
        title={title}
        src={src}
        className="h-[360px] w-full bg-background"
        sandbox="allow-same-origin allow-scripts allow-forms"
      />
      <p className="sr-only">Grafana panel unavailable</p>
    </div>
  );
}
