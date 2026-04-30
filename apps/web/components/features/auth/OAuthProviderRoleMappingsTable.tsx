"use client";

import { useEffect, useMemo, useState } from "react";
import { Plus, Save, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useToast } from "@/lib/hooks/use-toast";
import { useAdminOAuthProviderMutation } from "@/lib/hooks/use-oauth";
import type { OAuthProviderAdminResponse, OAuthProviderType } from "@/lib/types/oauth";

const ROLE_OPTIONS = [
  "user",
  "admin",
  "super_admin",
  "security_officer",
  "member",
  "viewer",
];
const GOOGLE_GROUP_RE = /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i;
const GITHUB_TEAM_RE = /^[a-z0-9-]+\/[a-z0-9-]+$/i;

interface MappingRow {
  id: string;
  group: string;
  role: string;
}

function rowsFromMapping(mapping: Record<string, string>): MappingRow[] {
  return Object.entries(mapping).map(([group, role], index) => ({
    id: `${group}-${index}`,
    group,
    role,
  }));
}

function validateGroup(providerType: OAuthProviderType, group: string): boolean {
  return providerType === "google"
    ? GOOGLE_GROUP_RE.test(group)
    : GITHUB_TEAM_RE.test(group);
}

export function OAuthProviderRoleMappingsTable({
  provider,
}: {
  provider: OAuthProviderAdminResponse;
}) {
  const t = useTranslations("admin.oauth");
  const { toast } = useToast();
  const mutation = useAdminOAuthProviderMutation();
  const [rows, setRows] = useState<MappingRow[]>(() =>
    rowsFromMapping(provider.group_role_mapping),
  );
  const invalidGroups = useMemo(
    () =>
      rows
        .map((row) => row.group.trim())
        .filter((group) => group && !validateGroup(provider.provider_type, group)),
    [provider.provider_type, rows],
  );
  const mapping = useMemo(
    () =>
      rows.reduce<Record<string, string>>((accumulator, row) => {
        const group = row.group.trim();
        const role = row.role.trim();
        if (group && role) {
          accumulator[group] = role;
        }
        return accumulator;
      }, {}),
    [rows],
  );

  useEffect(() => {
    setRows(rowsFromMapping(provider.group_role_mapping));
  }, [provider.group_role_mapping]);

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-md border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("roleMappings.group")}</TableHead>
              <TableHead>{t("roleMappings.role")}</TableHead>
              <TableHead className="w-16">{t("roleMappings.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <Input
                    aria-label={t("roleMappings.group")}
                    onChange={(event) => {
                      setRows((current) =>
                        current.map((item) =>
                          item.id === row.id
                            ? { ...item, group: event.target.value }
                            : item,
                        ),
                      );
                    }}
                    placeholder={
                      provider.provider_type === "google"
                        ? "admins@example.com"
                        : "org/team"
                    }
                    value={row.group}
                  />
                </TableCell>
                <TableCell>
                  <Select
                    aria-label={t("roleMappings.role")}
                    onChange={(event) => {
                      setRows((current) =>
                        current.map((item) =>
                          item.id === row.id
                            ? { ...item, role: event.target.value }
                            : item,
                        ),
                      );
                    }}
                    value={row.role}
                  >
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </Select>
                </TableCell>
                <TableCell>
                  <Button
                    aria-label={t("roleMappings.delete")}
                    onClick={() =>
                      setRows((current) => current.filter((item) => item.id !== row.id))
                    }
                    size="icon"
                    variant="ghost"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 ? (
              <TableRow>
                <TableCell className="text-muted-foreground" colSpan={3}>
                  {t("roleMappings.empty")}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>
      {invalidGroups.length > 0 ? (
        <p className="text-sm text-destructive">{t("roleMappings.invalidGroup")}</p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button
          onClick={() =>
            setRows((current) => [
              ...current,
              { id: `new-${Date.now()}`, group: "", role: "member" },
            ])
          }
          variant="outline"
        >
          <Plus className="h-4 w-4" />
          {t("roleMappings.add")}
        </Button>
        <Button
          disabled={invalidGroups.length > 0 || mutation.isPending}
          onClick={async () => {
            try {
              await mutation.mutateAsync({
                providerType: provider.provider_type,
                payload: {
                  client_id: provider.client_id,
                  client_secret_ref: provider.client_secret_ref,
                  default_role: provider.default_role,
                  display_name: provider.display_name,
                  domain_restrictions: provider.domain_restrictions,
                  enabled: provider.enabled,
                  group_role_mapping: mapping,
                  org_restrictions: provider.org_restrictions,
                  redirect_uri: provider.redirect_uri,
                  require_mfa: provider.require_mfa,
                  scopes: provider.scopes,
                },
              });
              toast({ title: t("roleMappings.saved"), variant: "success" });
            } catch (error) {
              toast({
                title: t("roleMappings.saveFailed"),
                description: error instanceof Error ? error.message : undefined,
                variant: "destructive",
              });
            }
          }}
        >
          <Save className="h-4 w-4" />
          {t("actions.save")}
        </Button>
      </div>
    </div>
  );
}
