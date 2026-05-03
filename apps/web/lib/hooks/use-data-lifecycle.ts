"use client";

import * as dl from "@/lib/api/data-lifecycle";
import { useAppMutation, useAppQuery } from "@/lib/hooks/use-api";

export const dataLifecycleKeys = {
  workspaceExportJobs: (workspaceId: string) =>
    ["data-lifecycle", "workspace", workspaceId, "export-jobs"] as const,
  workspaceExportJob: (workspaceId: string, jobId: string) =>
    ["data-lifecycle", "workspace", workspaceId, "export-jobs", jobId] as const,
  workspaceDeletionJob: (workspaceId: string, jobId: string) =>
    ["data-lifecycle", "workspace", workspaceId, "deletion-jobs", jobId] as const,
  tenantDeletionJob: (tenantId: string, jobId: string) =>
    ["data-lifecycle", "tenant", tenantId, "deletion-jobs", jobId] as const,
  subProcessorsAdmin: ["data-lifecycle", "admin", "sub-processors"] as const,
  dpaMetadata: (tenantId: string) =>
    ["data-lifecycle", "admin", "dpa", tenantId] as const,
};

export function useWorkspaceExportJobs(
  workspaceId: string,
  params?: { limit?: number; status?: string },
) {
  return useAppQuery(
    dataLifecycleKeys.workspaceExportJobs(workspaceId),
    () => dl.listWorkspaceExportJobs(workspaceId, params),
    { enabled: workspaceId.length > 0 },
  );
}

export function useWorkspaceExportJob(workspaceId: string, jobId: string | null) {
  return useAppQuery(
    dataLifecycleKeys.workspaceExportJob(workspaceId, jobId ?? ""),
    () => dl.getWorkspaceExportJob(workspaceId, jobId as string),
    {
      enabled: workspaceId.length > 0 && Boolean(jobId),
      refetchInterval: (query) => {
        const job = query.state.data as dl.ExportJob | undefined;
        if (!job) return 5_000;
        return job.status === "pending" || job.status === "processing"
          ? 5_000
          : false;
      },
    },
  );
}

export function useRequestWorkspaceExport(workspaceId: string) {
  return useAppMutation(() => dl.requestWorkspaceExport(workspaceId), {
    invalidateKeys: [dataLifecycleKeys.workspaceExportJobs(workspaceId)],
  });
}

export function useRequestWorkspaceDeletion(workspaceId: string) {
  return useAppMutation(
    (body: dl.DeletionRequest) => dl.requestWorkspaceDeletion(workspaceId, body),
  );
}

export function useWorkspaceDeletionJob(workspaceId: string, jobId: string | null) {
  return useAppQuery(
    dataLifecycleKeys.workspaceDeletionJob(workspaceId, jobId ?? ""),
    () => dl.getWorkspaceDeletionJob(workspaceId, jobId as string),
    { enabled: workspaceId.length > 0 && Boolean(jobId) },
  );
}

export function useCancelWorkspaceDeletion() {
  return useAppMutation((token: string) => dl.cancelWorkspaceDeletion(token));
}

export function useRequestTenantExport(tenantId: string) {
  return useAppMutation(() => dl.requestTenantExport(tenantId));
}

export function useRequestTenantDeletion(tenantId: string) {
  return useAppMutation(
    (vars: { body: dl.TenantDeletionRequest; twoPaToken: string }) =>
      dl.requestTenantDeletion(tenantId, vars.body, vars.twoPaToken),
  );
}

export function useTenantDeletionJob(tenantId: string, jobId: string | null) {
  return useAppQuery(
    dataLifecycleKeys.tenantDeletionJob(tenantId, jobId ?? ""),
    () => dl.getTenantDeletionJob(tenantId, jobId as string),
    { enabled: tenantId.length > 0 && Boolean(jobId) },
  );
}

export function useSubProcessorsAdmin() {
  return useAppQuery(dataLifecycleKeys.subProcessorsAdmin, () =>
    dl.listSubProcessorsAdmin(),
  );
}

export function useAddSubProcessor() {
  return useAppMutation(
    (body: dl.SubProcessorCreate) => dl.addSubProcessor(body),
    { invalidateKeys: [dataLifecycleKeys.subProcessorsAdmin] },
  );
}

export function useUpdateSubProcessor() {
  return useAppMutation(
    (vars: {
      id: string;
      body: Partial<dl.SubProcessorCreate> & { is_active?: boolean };
    }) => dl.updateSubProcessor(vars.id, vars.body),
    { invalidateKeys: [dataLifecycleKeys.subProcessorsAdmin] },
  );
}

export function useDeleteSubProcessor() {
  return useAppMutation((id: string) => dl.deleteSubProcessor(id), {
    invalidateKeys: [dataLifecycleKeys.subProcessorsAdmin],
  });
}

export function useDPAMetadata(tenantId: string) {
  return useAppQuery(
    dataLifecycleKeys.dpaMetadata(tenantId),
    () => dl.getDPAMetadata(tenantId),
    { enabled: tenantId.length > 0 },
  );
}

export function useUploadDPA(tenantId: string) {
  return useAppMutation(
    (vars: { file: File; version: string; effective_date: string }) =>
      dl.uploadDPA(tenantId, vars.file, vars.version, vars.effective_date),
    { invalidateKeys: [dataLifecycleKeys.dpaMetadata(tenantId)] },
  );
}

export function useGenerateArticle28Evidence(tenantId: string) {
  return useAppMutation(() => dl.generateArticle28Evidence(tenantId));
}
