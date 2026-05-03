"use client";

import { useTranslations } from "next-intl";
import { AlertCircle, CheckCircle2, Circle, ExternalLink } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { UserAlertItem } from "@/lib/schemas/me";

function formatTimestamp(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function severityIcon(urgency: string) {
  if (urgency === "critical") {
    return <AlertCircle className="h-4 w-4 text-destructive" />;
  }
  if (urgency === "warning") {
    return <AlertCircle className="h-4 w-4 text-amber-600" />;
  }
  return <Circle className="h-4 w-4 text-brand-accent" />;
}

interface NotificationListItemProps {
  alert: UserAlertItem;
  selected: boolean;
  onSelectedChange: (selected: boolean) => void;
}

export function NotificationListItem({
  alert,
  selected,
  onSelectedChange,
}: NotificationListItemProps) {
  const t = useTranslations("notifications.inbox.item");
  const templateT = useTranslations("creator.template");
  const href =
    typeof alert.source_reference?.url === "string"
      ? alert.source_reference.url
      : typeof alert.source_reference?.deep_link === "string"
        ? alert.source_reference.deep_link
        : null;
  const isTemplateUpdate = alert.alert_type === "creator.contract_template.upstream_updated";
  const isBillingOverage = alert.alert_type === "billing.overage.required";
  // UPD-049 refresh (102) T056/T057 — marketplace source-updated alert.
  // Rendered when the public agent a fork was based on has a new
  // approved version. Deep-links to the source detail page; the body
  // already includes the "fork has NOT been auto-updated" sentence.
  const isMarketplaceSourceUpdated =
    alert.alert_type === "marketplace.source_updated";
  const sourceUpdatedHref = isMarketplaceSourceUpdated
    ? typeof alert.source_reference?.source_agent_id === "string"
      ? `/marketplace?source_agent_id=${encodeURIComponent(
          alert.source_reference.source_agent_id,
        )}`
      : null
    : null;
  const resolvedHref = sourceUpdatedHref ?? href;

  return (
    <article className="grid gap-3 border-b border-border px-4 py-4 last:border-b-0 sm:grid-cols-[auto_1fr_auto]">
      <Checkbox
        aria-label={t("selectAria", { title: alert.title })}
        checked={selected}
        className="mt-1"
        onChange={(event) => onSelectedChange(event.target.checked)}
      />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          {severityIcon(alert.urgency)}
          <h3 className="truncate text-sm font-semibold">{alert.title}</h3>
          {alert.read ? (
            <Badge variant="secondary">
              <CheckCircle2 className="h-3 w-3" />
              {t("read")}
            </Badge>
          ) : (
            <Badge variant="outline">{t("unread")}</Badge>
          )}
          <Badge variant={isBillingOverage ? "destructive" : "secondary"}>
            {t(`severity.${alert.urgency}`)}
          </Badge>
        </div>
        {alert.body ? (
          <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{alert.body}</p>
        ) : null}
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>{alert.alert_type}</span>
          <span>{formatTimestamp(alert.created_at)}</span>
        </div>
      </div>
      {resolvedHref ? (
        <Button
          size="sm"
          variant="outline"
          data-testid={
            isMarketplaceSourceUpdated
              ? "marketplace-source-updated-open"
              : undefined
          }
          onClick={() => {
            window.location.assign(resolvedHref);
          }}
        >
          <ExternalLink className="h-4 w-4" />
          {isBillingOverage
            ? "Authorise now"
            : isTemplateUpdate
              ? templateT("viewDiff")
              : isMarketplaceSourceUpdated
                ? "Open source agent"
                : t("open")}
        </Button>
      ) : null}
    </article>
  );
}
