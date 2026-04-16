"use client";

import { useState } from "react";
import { GripVertical, ShieldPlus } from "lucide-react";
import { SearchInput } from "@/components/shared/SearchInput";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePolicyCatalog } from "@/lib/hooks/use-policy-catalog";

export interface PolicyCatalogProps {
  workspaceId: string;
  onAttach: (policyId: string) => void;
  onPolicyDragStart: (policyId: string, policyName: string) => void;
  onPolicyDragEnd: () => void;
}

export function PolicyCatalog({
  workspaceId,
  onAttach,
  onPolicyDragStart,
  onPolicyDragEnd,
}: PolicyCatalogProps) {
  const [search, setSearch] = useState("");
  const policyCatalogQuery = usePolicyCatalog(workspaceId, search);

  return (
    <Card className="h-full rounded-[1.75rem]">
      <CardHeader className="space-y-4">
        <div className="space-y-1">
          <CardTitle>Policy catalog</CardTitle>
          <p className="text-sm text-muted-foreground">
            Drag policies into the binding zone or use the keyboard fallback button.
          </p>
        </div>
        <SearchInput
          defaultValue=""
          isLoading={policyCatalogQuery.isFetching}
          placeholder="Search policies"
          onChange={setSearch}
        />
      </CardHeader>
      <CardContent className="space-y-3">
        {policyCatalogQuery.isLoading
          ? Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-28 rounded-[1.5rem]" />
            ))
          : policyCatalogQuery.data?.items.map((policy) => (
              <div
                key={policy.id}
                className="rounded-[1.5rem] border border-border/60 bg-background/70 p-4"
                draggable
                onDragEnd={onPolicyDragEnd}
                onDragStart={(event) => {
                  event.dataTransfer.setData("policyId", policy.id);
                  event.dataTransfer.setData("policyName", policy.name);
                  onPolicyDragStart(policy.id, policy.name);
                }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <GripVertical className="h-4 w-4 text-muted-foreground" />
                      <p className="font-medium">{policy.name}</p>
                    </div>
                    <Badge variant="outline">{policy.scopeType}</Badge>
                    <p className="text-sm text-muted-foreground">
                      {policy.description ?? "No description available."}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onAttach(policy.id)}
                  >
                    <ShieldPlus className="h-4 w-4" />
                    Attach
                  </Button>
                </div>
              </div>
            ))}
      </CardContent>
    </Card>
  );
}
