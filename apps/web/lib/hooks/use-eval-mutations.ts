"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createApiClient } from "@/lib/api";
import {
  evalQueryKeys,
  type AbExperimentResponse,
  type ATERunResponse,
  type BenchmarkCaseCreateInput,
  type BenchmarkCaseResponse,
  type EvalSetCreateInput,
  type EvalSetResponse,
  type EvaluationRunResponse,
} from "@/types/evaluation";

const evaluationApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface AddCaseVariables {
  evalSetId: string;
  payload: BenchmarkCaseCreateInput;
}

interface RunEvalVariables {
  evalSetId: string;
  agentFqn: string;
}

interface CreateExperimentVariables {
  runAId: string;
  runBId: string;
  name: string;
}

interface RunAteVariables {
  ateConfigId: string;
  agentFqn: string;
}

export function useEvalMutations() {
  const queryClient = useQueryClient();

  const invalidateEvalQueries = async () => {
    await queryClient.invalidateQueries({ queryKey: evalQueryKeys.root });
  };

  const createEvalSet = useMutation({
    mutationFn: (payload: EvalSetCreateInput) =>
      evaluationApi.post<EvalSetResponse>("/api/v1/evaluations/eval-sets", payload),
    onSuccess: invalidateEvalQueries,
  });

  const addCase = useMutation({
    mutationFn: ({ evalSetId, payload }: AddCaseVariables) =>
      evaluationApi.post<BenchmarkCaseResponse>(
        `/api/v1/evaluations/eval-sets/${encodeURIComponent(evalSetId)}/cases`,
        payload,
      ),
    onSuccess: invalidateEvalQueries,
  });

  const runEval = useMutation({
    mutationFn: ({ evalSetId, agentFqn }: RunEvalVariables) =>
      evaluationApi.post<EvaluationRunResponse>(
        `/api/v1/evaluations/eval-sets/${encodeURIComponent(evalSetId)}/run`,
        { agent_fqn: agentFqn },
      ),
    onSuccess: invalidateEvalQueries,
  });

  const createExperiment = useMutation({
    mutationFn: ({ runAId, runBId, name }: CreateExperimentVariables) =>
      evaluationApi.post<AbExperimentResponse>("/api/v1/evaluations/experiments", {
        run_a_id: runAId,
        run_b_id: runBId,
        name,
      }),
    onSuccess: invalidateEvalQueries,
  });

  const runAte = useMutation({
    mutationFn: ({ ateConfigId, agentFqn }: RunAteVariables) =>
      evaluationApi.post<ATERunResponse>(
        `/api/v1/evaluations/ate/${encodeURIComponent(ateConfigId)}/run/${encodeURIComponent(agentFqn)}`,
      ),
    onSuccess: invalidateEvalQueries,
  });

  return {
    createEvalSet,
    addCase,
    runEval,
    createExperiment,
    runAte,
  };
}
