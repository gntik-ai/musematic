"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputOTPProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> {
  value: string;
  onChange: (value: string) => void;
  maxLength?: number;
}

function sanitizeValue(value: string, inputMode: React.HTMLAttributes<HTMLInputElement>["inputMode"]) {
  if (inputMode === "numeric") {
    return value.replace(/\D/g, "");
  }

  return value;
}

export const InputOTP = React.forwardRef<HTMLInputElement, InputOTPProps>(
  (
    {
      className,
      inputMode = "numeric",
      maxLength = 6,
      onChange,
      value,
      ...props
    },
    ref,
  ) => (
    <input
      ref={ref}
      autoComplete="one-time-code"
      className={cn(
        "flex h-12 w-full rounded-md border border-input bg-background px-4 py-2 text-center font-mono text-lg tracking-[0.5em] ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      inputMode={inputMode}
      maxLength={maxLength}
      onChange={(event) => {
        onChange(sanitizeValue(event.target.value, inputMode).slice(0, maxLength));
      }}
      value={value}
      {...props}
    />
  ),
);

InputOTP.displayName = "InputOTP";

export function InputOTPGroup({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex items-center justify-center gap-2", className)} {...props} />;
}

export function InputOTPSlot({
  className,
  value,
}: React.HTMLAttributes<HTMLDivElement> & { value?: string }) {
  return (
    <div
      className={cn(
        "flex h-12 w-10 items-center justify-center rounded-md border border-input bg-background font-mono text-lg",
        className,
      )}
    >
      {value ?? ""}
    </div>
  );
}
