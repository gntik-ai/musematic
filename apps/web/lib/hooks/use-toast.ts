"use client";

export interface ToastPayload {
  title: string;
  description?: string | undefined;
  variant?: "default" | "destructive" | "success" | undefined;
  duration?: number | undefined;
}

export const TOAST_EVENT = "musematic:toast";

export function toast(payload: ToastPayload): void {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(new CustomEvent<ToastPayload>(TOAST_EVENT, { detail: payload }));
}

export function useToast(): { toast: typeof toast } {
  return { toast };
}
