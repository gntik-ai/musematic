"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

const channelSchema = z.discriminatedUnion("channel", [
  z.object({
    channel: z.literal("email"),
    email: z.string().email(),
    scopeComponents: z.string().optional(),
  }),
  z.object({
    channel: z.literal("webhook"),
    url: z.string().url(),
    contactEmail: z.string().email().optional().or(z.literal("")),
    scopeComponents: z.string().optional(),
  }),
  z.object({
    channel: z.literal("slack"),
    webhookUrl: z.string().url(),
    scopeComponents: z.string().optional(),
  }),
]);

type SubscribeValues = z.infer<typeof channelSchema>;
type Channel = SubscribeValues["channel"];

const API_BASE = process.env.NEXT_PUBLIC_STATUS_API_URL ?? "";
const CHANNEL_LABELS: Record<Channel, string> = {
  email: "Email updates",
  webhook: "Webhook",
  slack: "Slack",
};

export function SubscribeForm() {
  const [channel, setChannel] = useState<Channel>("email");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SubscribeValues>({
    defaultValues: { channel: "email", email: "", scopeComponents: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setMessage(null);
    setError(null);
    const parsed = channelSchema.safeParse({ ...values, channel });
    if (!parsed.success) {
      setError("Check the highlighted fields and try again.");
      return;
    }

    const scope_components = parseScope(parsed.data.scopeComponents);
    const endpoint = `/api/v1/public/subscribe/${channel}`;
    const body =
      parsed.data.channel === "email"
        ? { email: parsed.data.email, scope_components }
        : parsed.data.channel === "webhook"
          ? {
              url: parsed.data.url,
              contact_email: parsed.data.contactEmail || null,
              scope_components,
            }
          : { webhook_url: parsed.data.webhookUrl, scope_components };

    const response = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      setError("Subscription could not be saved right now.");
      return;
    }

    setMessage(
      channel === "email"
        ? "If that address is valid, a confirmation link has been sent."
        : "Subscription request accepted. Test delivery status will appear in your receiver.",
    );
  });

  return (
    <form className="grid gap-5" onSubmit={onSubmit}>
      <fieldset className="grid gap-2">
        <legend className="text-sm font-medium">Delivery channel</legend>
        <div className="grid gap-2 sm:grid-cols-3">
          {(["email", "webhook", "slack"] as const).map((item) => (
            <label key={item} className="flex items-center gap-2 rounded-md border p-3">
              <input
                type="radio"
                value={item}
                {...register("channel")}
                checked={channel === item}
                onChange={() => setChannel(item)}
              />
              <span>{CHANNEL_LABELS[item]}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {channel === "email" ? (
        <Field label="Email">
          <input
            className="h-10 rounded-md border bg-background px-3"
            placeholder="name@example.com"
            type="email"
            {...register("email")}
          />
          {errors.channel?.message ? <ErrorText value={errors.channel.message} /> : null}
        </Field>
      ) : null}

      {channel === "webhook" ? (
        <>
          <Field label="Webhook URL">
            <input
              className="h-10 rounded-md border bg-background px-3"
              placeholder="https://example.com/status-webhook"
              type="url"
              {...register("url")}
            />
          </Field>
          <Field label="Contact email">
            <input
              className="h-10 rounded-md border bg-background px-3"
              placeholder="ops@example.com"
              type="email"
              {...register("contactEmail")}
            />
          </Field>
        </>
      ) : null}

      {channel === "slack" ? (
        <Field label="Slack incoming webhook URL">
          <input
            className="h-10 rounded-md border bg-background px-3"
            placeholder="https://hooks.slack.com/services/..."
            type="url"
            {...register("webhookUrl")}
          />
        </Field>
      ) : null}

      <Field label="Component scope">
        <input
          className="h-10 rounded-md border bg-background px-3"
          placeholder="control-plane-api, reasoning-engine"
          {...register("scopeComponents")}
        />
      </Field>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {message ? <p className="text-sm text-emerald-700">{message}</p> : null}

      <div>
        <button
          className="inline-flex h-10 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
          disabled={isSubmitting}
          type="submit"
        >
          Subscribe
        </button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-2 text-sm font-medium">
      <span>{label}</span>
      {children}
    </label>
  );
}

function ErrorText({ value }: { value: string }) {
  return <p className="text-sm text-red-700">{value}</p>;
}

function parseScope(value?: string) {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
