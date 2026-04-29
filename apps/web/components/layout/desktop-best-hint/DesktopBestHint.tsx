"use client";

import Link from "next/link";
import { MonitorSmartphone } from "lucide-react";
import { usePathname } from "next/navigation";
import { useMediaQuery } from "@/lib/hooks/use-media-query";

const desktopPreferredRoutes = [
  {
    prefix: "/workflow-editor-monitor",
    readOnlyHref: "/workflow-editor-monitor",
    label: "Workflow Studio",
  },
  {
    prefix: "/fleet",
    readOnlyHref: "/fleet",
    label: "Fleet topology",
  },
  {
    prefix: "/admin/settings",
    readOnlyHref: "/admin/settings",
    label: "Admin settings",
  },
] as const;

export function DesktopBestHint() {
  const pathname = usePathname();
  const isMobile = useMediaQuery("(max-width: 767px)");
  const route = desktopPreferredRoutes.find((item) => pathname.startsWith(item.prefix));

  if (!isMobile || !route) {
    return null;
  }

  return (
    <div className="mb-4 rounded-lg border border-warning/50 bg-warning/10 p-4 text-sm" data-testid="desktop-best-hint">
      <div className="flex items-start gap-3">
        <MonitorSmartphone className="mt-0.5 h-5 w-5 shrink-0 text-foreground" />
        <div>
          <p className="font-semibold">{route.label} is best experienced on desktop.</p>
          <p className="mt-1 text-muted-foreground">
            Mobile keeps read-only viewing available while editing remains desktop-first.
          </p>
          <Link className="mt-2 inline-flex font-medium text-primary underline-offset-4 hover:underline" href={route.readOnlyHref}>
            Continue in read-only view
          </Link>
        </div>
      </div>
    </div>
  );
}
