"use client";

import { useTranslations } from "next-intl";
import { Lock } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { NotificationChannel } from "@/lib/schemas/me";

export const notificationChannels: NotificationChannel[] = [
  "in_app",
  "email",
  "webhook",
  "slack",
  "teams",
  "sms",
];

export const notificationEvents = [
  "security.login",
  "security.api_key.created",
  "incidents.created",
  "incidents.resolved",
  "execution.failed",
  "execution.completed",
  "workspace.goal.completed",
  "budget.threshold_reached",
] as const;

function isMandatoryEvent(eventType: string): boolean {
  return eventType.startsWith("security.") || eventType.startsWith("incidents.");
}

interface EventChannelMatrixProps {
  value: Record<string, NotificationChannel[]>;
  onChange: (value: Record<string, NotificationChannel[]>) => void;
}

export function EventChannelMatrix({ value, onChange }: EventChannelMatrixProps) {
  const t = useTranslations("notifications.preferences.matrix");

  function toggleChannel(eventType: string, channel: NotificationChannel, checked: boolean) {
    const current = value[eventType] ?? notificationChannels;
    const nextChannels = checked
      ? [...new Set([...current, channel])]
      : current.filter((item) => item !== channel);
    if (isMandatoryEvent(eventType) && nextChannels.length === 0) {
      return;
    }
    onChange({ ...value, [eventType]: nextChannels });
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[760px] text-sm">
        <thead className="border-b border-border bg-muted/40">
          <tr>
            <th className="w-[240px] px-3 py-3 text-left font-medium">
              {t("event")}
            </th>
            {notificationChannels.map((channel) => (
              <th key={channel} className="px-3 py-3 text-left font-medium">
                {t(`channels.${channel}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {notificationEvents.map((eventType) => {
            const mandatory = isMandatoryEvent(eventType);
            const enabledChannels = value[eventType] ?? notificationChannels;
            return (
              <tr key={eventType} className="border-b border-border last:border-b-0">
                <td className="px-3 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{eventType}</span>
                    {mandatory ? (
                      <Tooltip>
                        <TooltipTrigger>
                          <Lock className="h-3.5 w-3.5 text-muted-foreground" />
                        </TooltipTrigger>
                        <TooltipContent>{t("mandatoryTooltip")}</TooltipContent>
                      </Tooltip>
                    ) : null}
                  </div>
                </td>
                {notificationChannels.map((channel) => {
                  const checked = enabledChannels.includes(channel);
                  const disabled = mandatory && checked && enabledChannels.length === 1;
                  return (
                    <td key={channel} className="px-3 py-3">
                      <Checkbox
                        aria-label={t("channelAria", {
                          eventType,
                          channel: t(`channels.${channel}`),
                        })}
                        checked={checked}
                        disabled={disabled}
                        onChange={(event) =>
                          toggleChannel(eventType, channel, event.target.checked)
                        }
                      />
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
