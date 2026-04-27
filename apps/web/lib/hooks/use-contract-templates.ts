"use client";

import { fetchContractTemplates, forkContractTemplate } from "@/lib/api/creator-uis";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export function useContractTemplates() {
  return useAppQuery(["contract-templates"], fetchContractTemplates);
}

export function useForkContractTemplate() {
  return useAppMutation(
    async ({ templateId, newName }: { templateId: string; newName: string }) =>
      forkContractTemplate(templateId, newName),
    { invalidateKeys: [["contract-templates"]] },
  );
}

