"use client";

import { useParams } from "next/navigation";
import { EmptyState } from "@/components/shared/EmptyState";
import { PostMortemComposer } from "@/components/features/incident-response";
import { useAppMutation } from "@/lib/hooks/use-api";
import {
  distributePostMortem,
  markPostMortemBlameless,
  updatePostMortemSections,
  usePostMortemByIncident,
} from "@/lib/api/incidents";

export default function OperatorPostMortemPage() {
  const params = useParams<{ incidentId: string }>();
  const incidentId = params.incidentId;
  const postMortem = usePostMortemByIncident(incidentId);
  const save = useAppMutation(
    (payload: { id: string; impact_assessment: string; root_cause: string; action_items: unknown[] }) =>
      updatePostMortemSections(payload.id, payload),
  );
  const blameless = useAppMutation(markPostMortemBlameless);
  const distribute = useAppMutation((payload: { id: string; recipients: string[] }) =>
    distributePostMortem(payload.id, payload.recipients),
  );

  if (postMortem.isPending) {
    return <EmptyState title="Loading post-mortem" description="Fetching the draft." />;
  }
  if (!postMortem.data) {
    return <EmptyState title="Post-mortem unavailable" description="Start one from the incident detail." />;
  }

  return (
    <PostMortemComposer
      postMortem={postMortem.data}
      onDistribute={(recipients) =>
        distribute.mutate(
          { id: postMortem.data.id, recipients },
          { onSuccess: () => void postMortem.refetch() },
        )
      }
      onMarkBlameless={() =>
        blameless.mutate(postMortem.data.id, { onSuccess: () => void postMortem.refetch() })
      }
      onSaveSections={(payload) =>
        save.mutate(
          { id: postMortem.data.id, ...payload },
          { onSuccess: () => void postMortem.refetch() },
        )
      }
    />
  );
}
