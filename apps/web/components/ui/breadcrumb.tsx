import Link from "next/link";
import type * as React from "react";
import { cn } from "@/lib/utils";

export function Breadcrumb({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return <nav aria-label="Breadcrumb" className={cn("w-full", className)} {...props} />;
}

export function BreadcrumbList({ className, ...props }: React.OlHTMLAttributes<HTMLOListElement>) {
  return <ol className={cn("flex flex-wrap items-center gap-1.5 text-sm", className)} {...props} />;
}

export function BreadcrumbItem({ className, ...props }: React.LiHTMLAttributes<HTMLLIElement>) {
  return <li className={cn("inline-flex items-center gap-1.5", className)} {...props} />;
}

export function BreadcrumbLink({
  className,
  href,
  ...props
}: React.ComponentPropsWithoutRef<typeof Link>) {
  return <Link className={cn("transition-colors hover:text-foreground", className)} href={href} {...props} />;
}

export function BreadcrumbPage({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span aria-current="page" className={cn("font-medium text-foreground", className)} {...props} />;
}

export function BreadcrumbSeparator({
  className,
  children = "/",
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span aria-hidden="true" className={cn("text-muted-foreground", className)} {...props}>
      {children}
    </span>
  );
}
