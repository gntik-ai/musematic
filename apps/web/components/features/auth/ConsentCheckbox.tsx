"use client";

import Link from "next/link";
import { Checkbox } from "@/components/ui/checkbox";

interface ConsentCheckboxProps {
  value: boolean;
  onChange: (value: boolean) => void;
  consentVersion: string;
  type: "ai_disclosure" | "terms";
}

export function ConsentCheckbox({
  value,
  onChange,
  consentVersion,
  type,
}: ConsentCheckboxProps) {
  const id = `consent-${type}`;

  return (
    <label
      className="flex items-start gap-3 rounded-md border border-border/70 bg-muted/20 p-3 text-sm"
      htmlFor={id}
    >
      <Checkbox
        id={id}
        checked={value}
        onChange={(event) => onChange(event.currentTarget.checked)}
      />
      <span className="leading-5 text-muted-foreground">
        {type === "ai_disclosure" ? (
          <>
            I acknowledge the{" "}
            <Link className="font-medium text-brand-primary" href="/ai-disclosure">
              AI disclosure
            </Link>{" "}
            for this platform.
          </>
        ) : (
          <>
            I agree to the{" "}
            <Link className="font-medium text-brand-primary" href="/terms">
              terms
            </Link>{" "}
            and{" "}
            <Link className="font-medium text-brand-primary" href="/privacy">
              privacy policy
            </Link>
            .
          </>
        )}{" "}
        <span className="sr-only">Consent version {consentVersion}</span>
      </span>
    </label>
  );
}
