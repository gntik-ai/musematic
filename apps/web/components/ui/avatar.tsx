import * as React from "react";
import { cn } from "@/lib/utils";

export function Avatar({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("relative flex h-10 w-10 shrink-0 overflow-hidden rounded-full bg-muted", className)}
      {...props}
    />
  );
}

export function AvatarImage(props: React.ImgHTMLAttributes<HTMLImageElement>) {
  return <img className="aspect-square h-full w-full" {...props} />;
}

export function AvatarFallback({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn("flex h-full w-full items-center justify-center rounded-full bg-secondary font-medium", className)}
      {...props}
    />
  );
}
