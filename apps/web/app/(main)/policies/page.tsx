"use client";

import { useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus, ShieldCheck } from "lucide-react";
import { LabelExpressionEditor } from "@/components/features/tagging/LabelExpressionEditor";
import { TagLabelFilterToolbar } from "@/components/features/tagging/TagLabelFilterToolbar";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { usePolicyCatalog, usePolicyCreate } from "@/lib/hooks/use-policy-catalog";
import {
  parseTagLabelFilters,
  savedViewFiltersToSearchParams,
  writeTagLabelFilters,
} from "@/lib/tagging/filter-query";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";

export default function PoliciesPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const currentWorkspaceId = useWorkspaceStore(
    (state) => state.currentWorkspace?.id ?? null,
  );
  const authWorkspaceId = useAuthStore((state) => state.user?.workspaceId ?? null);
  const workspaceId = currentWorkspaceId ?? authWorkspaceId;
  const tagLabelFilters = useMemo(
    () => parseTagLabelFilters(searchParams),
    [searchParams],
  );
  const search = searchParams.get("search") ?? "";
  const policiesQuery = usePolicyCatalog(workspaceId, search, tagLabelFilters);
  const createPolicy = usePolicyCreate();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [labelExpression, setLabelExpression] = useState("");

  const replaceSearchParams = (nextParams: URLSearchParams) => {
    const nextQuery = nextParams.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname);
  };

  const createDisabled = !workspaceId || !name.trim() || createPolicy.isPending;

  if (!workspaceId) {
    return (
      <EmptyState
        description="Select a workspace before browsing policies."
        icon={ShieldCheck}
        title="Workspace required"
      />
    );
  }

  return (
    <section className="space-y-6">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight">Policies</h1>
          <p className="text-sm text-muted-foreground md:text-base">
            Review workspace policy coverage and enforcement scope.
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4" />
              New Policy
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl space-y-4">
            <DialogHeader>
              <DialogTitle>New Policy</DialogTitle>
            </DialogHeader>
            <div className="grid gap-3">
              <Input
                aria-label="Policy name"
                placeholder="Name"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
              <Textarea
                aria-label="Policy description"
                placeholder="Description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
              <LabelExpressionEditor
                value={labelExpression}
                onChange={setLabelExpression}
              />
            </div>
            <DialogFooter>
              <Button
                disabled={createDisabled}
                onClick={async () => {
                  if (!workspaceId) {
                    return;
                  }
                  await createPolicy.mutateAsync({
                    workspaceId,
                    name: name.trim(),
                    description: description.trim() || null,
                    labelExpression: labelExpression.trim() || null,
                  });
                  setName("");
                  setDescription("");
                  setLabelExpression("");
                  setDialogOpen(false);
                }}
              >
                Save
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </header>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <Input
          aria-label="Search policies"
          className="max-w-xl"
          placeholder="Search policies"
          value={search}
          onChange={(event) => {
            const nextParams = new URLSearchParams(searchParams.toString());
            if (event.target.value) {
              nextParams.set("search", event.target.value);
            } else {
              nextParams.delete("search");
            }
            replaceSearchParams(nextParams);
          }}
        />
        <p className="text-sm text-muted-foreground">
          {policiesQuery.data?.total ?? 0} policies in view
        </p>
      </div>

      <TagLabelFilterToolbar
        entityType="policy"
        savedViewFilters={{ search, ...tagLabelFilters }}
        value={tagLabelFilters}
        workspaceId={workspaceId}
        onApplySavedView={(savedFilters) =>
          replaceSearchParams(
            savedViewFiltersToSearchParams(searchParams, savedFilters, ["search"]),
          )
        }
        onChange={(nextFilters) =>
          replaceSearchParams(writeTagLabelFilters(searchParams, nextFilters))
        }
      />

      <div className="grid gap-3">
        {(policiesQuery.data?.items ?? []).map((policy) => (
          <article
            className="rounded-xl border border-border/70 bg-card/80 p-4 shadow-sm"
            key={policy.id}
          >
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div className="space-y-1">
                <h2 className="text-base font-semibold">{policy.name}</h2>
                <p className="text-sm text-muted-foreground">
                  {policy.description ?? "No description"}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline">{policy.scopeType}</Badge>
                <Badge variant={policy.status === "active" ? "default" : "secondary"}>
                  {policy.status}
                </Badge>
              </div>
            </div>
          </article>
        ))}
      </div>

      {!policiesQuery.isLoading && policiesQuery.data?.items.length === 0 ? (
        <EmptyState
          description="No policies match the active filters."
          icon={ShieldCheck}
          title="No policies"
        />
      ) : null}
    </section>
  );
}
