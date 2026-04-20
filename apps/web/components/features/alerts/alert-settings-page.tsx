"use client";

import { useEffect, useMemo, useState } from "react";
import { BellRing } from "lucide-react";
import { removeInteractionAlertMute } from "@/lib/alerts/interaction-mutes";
import { useAlertRules, useAlertRulesMutations } from "@/lib/hooks/use-alert-rules";
import { useAuthStore } from "@/store/auth-store";
import { useWorkspaceStore } from "@/store/workspace-store";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { AlertDeliveryMethod } from "@/types/alerts";

function groupLabel(transition: string): string {
  return transition.split(".")[0]?.replace(/_/g, " ") ?? transition;
}

function formatMutedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Date unavailable";
  }
  return date.toLocaleString();
}

export function AlertSettingsPage() {
  const userId = useAuthStore((state) => state.user?.id ?? null);
  const workspaceId = useWorkspaceStore((state) => state.currentWorkspace?.id ?? null);
  const { interactionMutes, isLoading, rules } = useAlertRules(userId, workspaceId);
  const mutation = useAlertRulesMutations(userId);
  const [enabledTransitions, setEnabledTransitions] = useState<string[]>([]);
  const [deliveryMethod, setDeliveryMethod] =
    useState<AlertDeliveryMethod>("in-app");
  const [muteSearch, setMuteSearch] = useState("");

  useEffect(() => {
    if (rules.length === 0) {
      return;
    }
    setEnabledTransitions(
      rules.filter((rule) => rule.enabled).map((rule) => rule.transitionType),
    );
    setDeliveryMethod(rules[0]?.deliveryMethod ?? "in-app");
  }, [rules]);

  const groupedRules = useMemo(() => {
    return rules.reduce<Record<string, typeof rules>>((acc, rule) => {
      const key = groupLabel(rule.transitionType);
      acc[key] = [...(acc[key] ?? []), rule];
      return acc;
    }, {});
  }, [rules]);

  const filteredInteractionMutes = useMemo(() => {
    const query = muteSearch.trim().toLowerCase();
    if (!query) {
      return interactionMutes;
    }

    return interactionMutes.filter((mute) =>
      mute.interactionId.toLowerCase().includes(query),
    );
  }, [interactionMutes, muteSearch]);

  const persistInteractionMutes = (nextInteractionMutes: typeof interactionMutes) => {
    mutation.mutate({
      deliveryMethod,
      interactionMutes: nextInteractionMutes,
      transitionTypes: enabledTransitions,
    });
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-brand-accent">
            <BellRing className="h-4 w-4" />
            <span className="text-sm font-semibold uppercase tracking-[0.2em]">Alerts</span>
          </div>
          <CardTitle>Alert settings</CardTitle>
          <p className="text-sm text-muted-foreground">
            Critical transitions are enabled by default. Adjust the rules below for your workspace.
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
            <div className="rounded-xl border border-border/60 bg-muted/30 p-4 text-sm text-muted-foreground">
              Recommended defaults keep high-signal failures and trust events visible while reducing idle noise.
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="delivery-method">Delivery method</label>
              <Select
                id="delivery-method"
                value={deliveryMethod}
                onChange={(event) => setDeliveryMethod(event.target.value as AlertDeliveryMethod)}
              >
                <option value="in-app">In-app</option>
                <option value="email">Email</option>
                <option value="both">Both</option>
              </Select>
            </div>
          </div>

          {Object.entries(groupedRules).map(([group, groupItems]) => (
            <Card key={group} className="border-dashed">
              <CardHeader>
                <CardTitle className="text-base">{group}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {groupItems.map((rule) => {
                  const checked = enabledTransitions.includes(rule.transitionType);
                  return (
                    <div className="flex items-center justify-between gap-4" key={rule.id}>
                      <div>
                        <p className="font-medium">{rule.transitionType}</p>
                        <p className="text-sm text-muted-foreground">
                          Notify when {rule.transitionType.replace(/[._]/g, " ")} occurs.
                        </p>
                      </div>
                      <Switch
                        checked={checked}
                        onCheckedChange={(next) => {
                          setEnabledTransitions((current) => {
                            if (next) {
                              return [...new Set([...current, rule.transitionType])];
                            }
                            return current.filter((item) => item !== rule.transitionType);
                          });
                        }}
                      />
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          ))}

          <Card className="border-dashed">
            <CardHeader>
              <CardTitle className="text-base">
                Muted interactions{interactionMutes.length > 0 ? ` (${interactionMutes.length})` : ""}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {interactionMutes.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No per-interaction mute overrides are configured yet.
                </p>
              ) : (
                <>
                  <Input
                    onChange={(event) => setMuteSearch(event.target.value)}
                    placeholder="Search muted interaction IDs"
                    value={muteSearch}
                  />
                  {filteredInteractionMutes.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No muted interactions match that query.
                    </p>
                  ) : (
                    <div className="space-y-3">
                      {filteredInteractionMutes.map((mute) => (
                        <div
                          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/60 bg-muted/20 px-4 py-3"
                          key={mute.interactionId}
                        >
                          <div className="space-y-1">
                            <p className="font-mono text-sm text-foreground">{mute.interactionId}</p>
                            <p className="text-xs text-muted-foreground">
                              Muted {formatMutedAt(mute.mutedAt)}
                            </p>
                          </div>
                          <Button
                            disabled={mutation.isPending}
                            onClick={() =>
                              persistInteractionMutes(
                                removeInteractionAlertMute(interactionMutes, mute.interactionId),
                              )
                            }
                            size="sm"
                            variant="outline"
                          >
                            Remove mute
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button
              disabled={isLoading || mutation.isPending}
              onClick={() =>
                mutation.mutate({
                  deliveryMethod,
                  transitionTypes: enabledTransitions,
                })
              }
            >
              Save alert settings
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
