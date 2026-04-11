"use client";

import { useMemo } from "react";
import { usePathname } from "next/navigation";
import {
  Breadcrumb as UIBreadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import type { BreadcrumbSegment } from "@/types/navigation";
import { toTitleCase } from "@/lib/utils";

function buildSegments(pathname: string): BreadcrumbSegment[] {
  if (pathname === "/") {
    return [];
  }

  const parts = pathname.split("/").filter(Boolean);

  return parts.map((part, index) => ({
    label: toTitleCase(part),
    href: index === parts.length - 1 ? null : `/${parts.slice(0, index + 1).join("/")}`,
  }));
}

export function Breadcrumb() {
  const pathname = usePathname();
  const segments = useMemo(() => buildSegments(pathname), [pathname]);

  if (segments.length === 0) {
    return <div className="text-sm text-muted-foreground">Home</div>;
  }

  return (
    <UIBreadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink href="/">Home</BreadcrumbLink>
        </BreadcrumbItem>
        {segments.map((segment) => (
          <BreadcrumbItem key={`${segment.label}-${segment.href ?? "current"}`}>
            <BreadcrumbSeparator />
            {segment.href ? <BreadcrumbLink href={segment.href}>{segment.label}</BreadcrumbLink> : <BreadcrumbPage>{segment.label}</BreadcrumbPage>}
          </BreadcrumbItem>
        ))}
      </BreadcrumbList>
    </UIBreadcrumb>
  );
}
