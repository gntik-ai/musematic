"use client";

import { useState, type DragEvent } from "react";
import { useToast } from "@/lib/hooks/use-toast";
import { useAttachPolicy, useDetachPolicy } from "@/lib/hooks/use-policy-actions";
import { useEffectivePolicies } from "@/lib/hooks/use-effective-policies";
import { usePolicyAttachmentStore } from "@/lib/stores/use-policy-attachment-store";
import { PolicyBindingList } from "@/components/features/trust-workbench/PolicyBindingList";
import { PolicyCatalog } from "@/components/features/trust-workbench/PolicyCatalog";

export interface PolicyAttachmentPanelProps {
  agentId: string;
  agentRevisionId: string;
  workspaceId: string;
}

export function PolicyAttachmentPanel({
  agentId,
  agentRevisionId,
  workspaceId,
}: PolicyAttachmentPanelProps) {
  const { toast } = useToast();
  const [isDragOver, setIsDragOver] = useState(false);
  const effectivePoliciesQuery = useEffectivePolicies(agentId, workspaceId);
  const attachPolicy = useAttachPolicy();
  const detachPolicy = useDetachPolicy();
  const {
    dropError,
    draggedPolicyName,
    clearDropError,
    endDrag,
    setDropError,
    startDrag,
  } = usePolicyAttachmentStore();

  const bindings = effectivePoliciesQuery.data ?? [];

  const handleAttach = async (policyId: string) => {
    if (!policyId) {
      return;
    }

    clearDropError();
    const alreadyAttached = bindings.some((binding) => binding.policyId === policyId);
    if (alreadyAttached) {
      setDropError(
        `${draggedPolicyName ?? "This policy"} is already attached to the selected revision.`,
      );
      return;
    }

    try {
      await attachPolicy.mutateAsync({
        policyId,
        agentId,
        agentRevisionId,
      });
      toast({
        title: "Policy attached",
        variant: "success",
      });
      clearDropError();
    } catch (error) {
      setDropError(
        error instanceof Error ? error.message : "Unable to attach the policy.",
      );
      toast({
        title: "Unable to attach the policy",
        description:
          error instanceof Error ? error.message : "Try again in a moment.",
        variant: "destructive",
      });
    } finally {
      setIsDragOver(false);
      endDrag();
    }
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragOver(true);
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
      <PolicyCatalog
        workspaceId={workspaceId}
        onAttach={handleAttach}
        onPolicyDragEnd={() => {
          setIsDragOver(false);
          endDrag();
        }}
        onPolicyDragStart={startDrag}
      />
      <PolicyBindingList
        bindings={bindings}
        dropError={dropError}
        isDragOver={isDragOver}
        isLoading={effectivePoliciesQuery.isLoading}
        onDragLeave={() => setIsDragOver(false)}
        onDragOver={handleDragOver}
        onDrop={(policyId) => {
          void handleAttach(policyId);
        }}
        onRemove={(attachmentId, policyId) => {
          void detachPolicy
            .mutateAsync({
              attachmentId,
              policyId,
              agentId,
            })
            .then(() => {
              toast({
                title: "Policy removed",
                variant: "success",
              });
            })
            .catch((error) => {
              toast({
                title: "Unable to remove the policy",
                description:
                  error instanceof Error ? error.message : "Try again in a moment.",
                variant: "destructive",
              });
            });
        }}
      />
    </div>
  );
}
