"use client";

/**
 * UPD-050 T079 — Geo-block policy admin page.
 *
 * Per `quickstart.md` Walkthrough 6 — super admin selects mode
 * (disabled / deny_list / allow_list) and edits the country-codes
 * list. Mode-switch requires explicit confirmation per
 * `contracts/geo-policy-rest.md`.
 */

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useAppQuery } from "@/lib/hooks/use-api";
import { createApiClient } from "@/lib/api";

const adminApi = createApiClient(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
);

interface GeoPolicy {
  mode: "disabled" | "deny_list" | "allow_list";
  country_codes: string[];
  geoip_db_loaded: boolean;
  geoip_db_version: string | null;
  updated_at: string;
  updated_by_user_id: string | null;
}

const geoPolicyKey = ["admin", "security", "geo-policy"] as const;

export default function GeoPolicyPage() {
  const client = useQueryClient();
  const policyQuery = useAppQuery<GeoPolicy>(geoPolicyKey, () =>
    adminApi.get<GeoPolicy>("/api/v1/admin/security/geo-policy"),
  );
  const [mode, setMode] = useState<GeoPolicy["mode"]>("disabled");
  const [countryCodes, setCountryCodes] = useState<string>("");
  const [confirm, setConfirm] = useState(false);

  useEffect(() => {
    if (policyQuery.data) {
      setMode(policyQuery.data.mode);
      setCountryCodes(policyQuery.data.country_codes.join(", "));
    }
  }, [policyQuery.data]);

  const update = useMutation({
    mutationFn: async (input: {
      mode: GeoPolicy["mode"];
      country_codes: string[];
      confirm_mode_switch: boolean;
    }) => adminApi.patch("/api/v1/admin/security/geo-policy", input),
    onSuccess: () => client.invalidateQueries({ queryKey: geoPolicyKey }),
  });

  const isModeSwitching = policyQuery.data && mode !== policyQuery.data.mode;

  const onSave = async () => {
    const codes = countryCodes
      .split(/[,\s]+/)
      .map((c) => c.trim().toUpperCase())
      .filter(Boolean);
    await update.mutateAsync({
      mode,
      country_codes: codes,
      confirm_mode_switch: isModeSwitching ? confirm : false,
    });
    setConfirm(false);
  };

  if (policyQuery.isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-normal">
          Geo-block policy
        </h1>
        <p className="text-sm text-muted-foreground">
          Per-country signup blocking. Off by default. Modes are mutually
          exclusive — switching mode resets the country list and requires
          explicit confirmation.
        </p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Status</CardTitle>
          <Badge
            variant={policyQuery.data?.geoip_db_loaded ? "outline" : "destructive"}
            data-testid="geoip-db-status"
          >
            GeoLite2 DB:{" "}
            {policyQuery.data?.geoip_db_loaded
              ? `loaded (${policyQuery.data?.geoip_db_version ?? "unknown"})`
              : "missing — graceful degradation"}
          </Badge>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Policy</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3">
          <div>
            <Label htmlFor="mode">Mode</Label>
            <select
              id="mode"
              className="block h-10 w-48 rounded-md border bg-background px-3"
              value={mode}
              onChange={(e) => setMode(e.target.value as GeoPolicy["mode"])}
              data-testid="geo-policy-mode-select"
            >
              <option value="disabled">Disabled</option>
              <option value="deny_list">Deny list (block listed)</option>
              <option value="allow_list">Allow list (block unlisted)</option>
            </select>
          </div>
          <div>
            <Label htmlFor="codes">
              Country codes (ISO-3166-1 alpha-2, comma-separated)
            </Label>
            <Input
              id="codes"
              placeholder="RU, KP"
              value={countryCodes}
              onChange={(e) => setCountryCodes(e.target.value)}
              data-testid="geo-policy-codes-input"
            />
          </div>
          {isModeSwitching ? (
            <div className="rounded-md border border-yellow-500/40 bg-yellow-500/10 p-3 text-sm">
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  checked={confirm}
                  onChange={(e) => setConfirm(e.target.checked)}
                  className="mt-1"
                  data-testid="geo-policy-confirm-checkbox"
                />
                <span>
                  I understand that switching mode resets the policy
                  semantics. Confirm to enable Save.
                </span>
              </label>
            </div>
          ) : null}
          <Button
            onClick={onSave}
            disabled={update.isPending || (isModeSwitching && !confirm)}
            className="self-start"
            data-testid="geo-policy-save"
          >
            Save
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
