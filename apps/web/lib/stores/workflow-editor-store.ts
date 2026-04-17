"use client";

import { create } from "zustand";
import type {
  ValidationError,
  WorkflowGraphEdge,
  WorkflowGraphNode,
} from "@/types/workflows";

export interface WorkflowEditorStoreState {
  yamlContent: string;
  validationErrors: ValidationError[];
  isDirty: boolean;
  isSaving: boolean;
  lastSavedVersionId: string | null;
  graphNodes: WorkflowGraphNode[];
  graphEdges: WorkflowGraphEdge[];
  parseError: string | null;
  setYamlContent: (yaml: string) => void;
  setValidationErrors: (errors: ValidationError[]) => void;
  setGraphState: (nodes: WorkflowGraphNode[], edges: WorkflowGraphEdge[]) => void;
  setParseError: (error: string | null) => void;
  setIsSaving: (value: boolean) => void;
  markSaved: (versionId: string) => void;
  reset: () => void;
}

const initialState = {
  yamlContent: "",
  validationErrors: [],
  isDirty: false,
  isSaving: false,
  lastSavedVersionId: null,
  graphNodes: [],
  graphEdges: [],
  parseError: null,
} satisfies Omit<
  WorkflowEditorStoreState,
  | "setYamlContent"
  | "setValidationErrors"
  | "setGraphState"
  | "setParseError"
  | "setIsSaving"
  | "markSaved"
  | "reset"
>;

export const useWorkflowEditorStore = create<WorkflowEditorStoreState>()(
  (set) => ({
    ...initialState,
    setYamlContent: (yamlContent) =>
      set(() => ({
        yamlContent,
        isDirty: true,
      })),
    setValidationErrors: (validationErrors) => set(() => ({ validationErrors })),
    setGraphState: (graphNodes, graphEdges) => set(() => ({ graphNodes, graphEdges })),
    setParseError: (parseError) => set(() => ({ parseError })),
    setIsSaving: (isSaving) => set(() => ({ isSaving })),
    markSaved: (versionId) =>
      set(() => ({
        isDirty: false,
        isSaving: false,
        lastSavedVersionId: versionId,
      })),
    reset: () => set(() => ({ ...initialState })),
  }),
);
