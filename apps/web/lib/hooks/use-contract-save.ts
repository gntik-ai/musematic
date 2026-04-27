"use client";

import {
  createContract,
  type AgentContractPayload,
  type AgentContractUpdatePayload,
  updateContract,
} from "@/lib/api/creator-uis";
import { useAppMutation } from "@/lib/hooks/use-api";

export function useContractSave(contractId?: string | null) {
  return useAppMutation(
    async (payload: AgentContractPayload | AgentContractUpdatePayload) => {
      if (contractId) {
        const updatePayload = { ...payload } as AgentContractPayload;
        delete (updatePayload as Partial<AgentContractPayload>).agent_id;
        return updateContract(contractId, updatePayload);
      }

      return createContract(payload as AgentContractPayload);
    },
  );
}
