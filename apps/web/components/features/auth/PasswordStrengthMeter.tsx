"use client";

import { CheckCircle2, Circle } from "lucide-react";
import { Progress } from "@/components/ui/progress";
import { evaluatePasswordRules } from "@/lib/schemas/auth-schemas";

interface PasswordStrengthMeterProps {
  password: string;
}

const DESCRIPTORS = [
  { label: "Weak", className: "bg-destructive" },
  { label: "Fair", className: "bg-amber-500" },
  { label: "Good", className: "bg-brand-accent" },
  { label: "Strong", className: "bg-emerald-500" },
] as const;

export function PasswordStrengthMeter({ password }: PasswordStrengthMeterProps) {
  const rules = evaluatePasswordRules(password);
  const satisfied = rules.filter((rule) => rule.satisfied).length;
  const descriptor = DESCRIPTORS[Math.min(Math.max(satisfied - 2, 0), 3)] ?? DESCRIPTORS[0];
  const value = (satisfied / rules.length) * 100;

  return (
    <div className="space-y-3" aria-live="polite">
      <div className="flex items-center gap-3">
        <Progress
          className="h-2"
          indicatorClassName={descriptor.className}
          value={value}
        />
        <span className="w-14 text-right text-xs font-medium text-muted-foreground">
          {descriptor.label}
        </span>
      </div>
      <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
        {rules.map((rule) => {
          const Icon = rule.satisfied ? CheckCircle2 : Circle;
          return (
            <div key={rule.key} className="flex items-center gap-2">
              <Icon
                className={
                  rule.satisfied ? "h-3.5 w-3.5 text-emerald-600" : "h-3.5 w-3.5"
                }
              />
              {rule.label}
            </div>
          );
        })}
      </div>
    </div>
  );
}
