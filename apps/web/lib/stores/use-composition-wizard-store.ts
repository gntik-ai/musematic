"use client";

import { create } from "zustand";
import type {
  CompositionBlueprint,
  CompositionWizardCustomizations,
  ValidationResult,
} from "@/lib/types/agent-management";

export interface CompositionWizardState {
  step: 1 | 2 | 3 | 4;
  description: string;
  blueprint: CompositionBlueprint | null;
  customizations: Partial<CompositionWizardCustomizations>;
  validation_result: ValidationResult | null;
  is_loading: boolean;
  error: string | null;
  setStep: (step: 1 | 2 | 3 | 4) => void;
  setDescription: (description: string) => void;
  setBlueprint: (blueprint: CompositionBlueprint | null) => void;
  applyCustomization: <TKey extends keyof CompositionWizardCustomizations>(
    field: TKey,
    value: CompositionWizardCustomizations[TKey],
  ) => void;
  setValidationResult: (result: ValidationResult | null) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  step: 1 as const,
  description: "",
  blueprint: null,
  customizations: {},
  validation_result: null,
  is_loading: false,
  error: null,
} satisfies Omit<
  CompositionWizardState,
  | "setStep"
  | "setDescription"
  | "setBlueprint"
  | "applyCustomization"
  | "setValidationResult"
  | "setLoading"
  | "setError"
  | "reset"
>;

export const useCompositionWizardStore = create<CompositionWizardState>()(
  (set) => ({
    ...initialState,
    setStep: (step) => set({ step }),
    setDescription: (description) => set({ description }),
    setBlueprint: (blueprint) => set({ blueprint }),
    applyCustomization: (field, value) =>
      set((state) => ({
        customizations: {
          ...state.customizations,
          [field]: value,
        },
      })),
    setValidationResult: (validation_result) => set({ validation_result }),
    setLoading: (is_loading) => set({ is_loading }),
    setError: (error) => set({ error }),
    reset: () => set({ ...initialState }),
  }),
);
