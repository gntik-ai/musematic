"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { QrCodeStep } from "@/components/features/auth/mfa-enrollment/QrCodeStep";
import { RecoveryCodesStep } from "@/components/features/auth/mfa-enrollment/RecoveryCodesStep";
import { VerificationStep } from "@/components/features/auth/mfa-enrollment/VerificationStep";

type MfaEnrollmentStep = "qr_display" | "verification" | "recovery_codes";

interface MfaEnrollmentDialogProps {
  allowSkip?: boolean;
  onEnrolled: () => void;
  onSkip?: () => void;
  open: boolean;
}

export function MfaEnrollmentDialog({
  allowSkip = false,
  onEnrolled,
  onSkip,
  open,
}: MfaEnrollmentDialogProps) {
  const [step, setStep] = useState<MfaEnrollmentStep>("qr_display");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [pulseAcknowledgement, setPulseAcknowledgement] = useState(false);

  useEffect(() => {
    if (!pulseAcknowledgement) {
      return undefined;
    }

    const timeoutId = window.setTimeout(() => {
      setPulseAcknowledgement(false);
    }, 1200);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [pulseAcknowledgement]);

  useEffect(() => {
    if (open) {
      setStep("qr_display");
      setRecoveryCodes([]);
      setPulseAcknowledgement(false);
    }
  }, [open]);

  const dialogDescription = useMemo(() => {
    if (step === "verification") {
      return "Confirm the authenticator code before Musematic will trust this device.";
    }

    if (step === "recovery_codes") {
      return "You must acknowledge that these recovery codes have been stored safely.";
    }

    return "Finish your multi-factor enrollment before continuing into the workspace.";
  }, [step]);

  const preventDismiss = () => {
    setPulseAcknowledgement(step === "recovery_codes");
  };

  return (
    <Dialog
      onOpenChange={(nextOpen) => {
        if (!nextOpen) {
          if (allowSkip && onSkip && step !== "recovery_codes") {
            onSkip();
            return;
          }

          preventDismiss();
        }
      }}
      open={open}
    >
      <DialogContent
        className="max-w-2xl"
        onEscapeKeyDown={(event) => {
          event.preventDefault();
          preventDismiss();
        }}
        onInteractOutside={(event) => {
          event.preventDefault();
          preventDismiss();
        }}
      >
        <DialogHeader className="sr-only">
          <DialogTitle>Set up multi-factor authentication</DialogTitle>
          <DialogDescription>{dialogDescription}</DialogDescription>
        </DialogHeader>

        {step === "qr_display" ? (
          <QrCodeStep
            allowSkip={allowSkip}
            onNext={() => {
              setStep("verification");
            }}
            onSkip={onSkip}
          />
        ) : null}

        {step === "verification" ? (
          <VerificationStep
            onBack={() => {
              setStep("qr_display");
            }}
            onSuccess={(codes) => {
              setRecoveryCodes(codes);
              setStep("recovery_codes");
            }}
          />
        ) : null}

        {step === "recovery_codes" ? (
          <RecoveryCodesStep
            onComplete={onEnrolled}
            pulseAcknowledge={pulseAcknowledgement}
            recoveryCodes={recoveryCodes}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
