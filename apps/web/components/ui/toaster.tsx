"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { Toast, type ToastVariant } from "@/components/ui/toast";
import { TOAST_EVENT, type ToastPayload } from "@/lib/hooks/use-toast";
import { cn } from "@/lib/utils";

interface ToastRecord extends ToastPayload {
  id: string;
  variant: ToastVariant;
}

export function Toaster() {
  const [toasts, setToasts] = useState<ToastRecord[]>([]);

  useEffect(() => {
    const handleToast = (event: Event) => {
      const customEvent = event as CustomEvent<ToastPayload>;
      const payload = customEvent.detail;
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const nextToast: ToastRecord = {
        id,
        variant: payload.variant ?? "default",
        title: payload.title,
        description: payload.description,
        duration: payload.duration ?? 4000,
      };

      setToasts((current) => [...current, nextToast]);

      window.setTimeout(() => {
        setToasts((current) => current.filter((toast) => toast.id !== id));
      }, nextToast.duration);
    };

    window.addEventListener(TOAST_EVENT, handleToast as EventListener);
    return () => {
      window.removeEventListener(TOAST_EVENT, handleToast as EventListener);
    };
  }, []);

  if (toasts.length === 0) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[60] flex w-full max-w-sm flex-col gap-3">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto relative">
          <button
            aria-label="Dismiss notification"
            className={cn(
              "absolute right-3 top-3 rounded-full p-1 transition",
              toast.variant === "destructive"
                ? "text-destructive-foreground/90 hover:bg-destructive-foreground/15"
                : "text-muted-foreground hover:bg-muted",
            )}
            onClick={() => {
              setToasts((current) => current.filter((item) => item.id !== toast.id));
            }}
            type="button"
          >
            <X className="h-3.5 w-3.5" />
          </button>
          <Toast
            description={toast.description}
            title={toast.title}
            variant={toast.variant}
          />
        </div>
      ))}
    </div>
  );
}
