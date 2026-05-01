"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useCreateStatusSubscription } from "@/lib/hooks/use-status-subscriptions";

const subscriptionFormSchema = z.object({
  channel: z.enum(["email", "webhook", "slack"]),
  target: z.string().min(3, "Target is required."),
  scope_components: z.string().optional(),
});
const channelTargetSchema = z.discriminatedUnion("channel", [
  z.object({ channel: z.literal("email"), target: z.string().email() }),
  z.object({ channel: z.literal("webhook"), target: z.string().url() }),
  z.object({ channel: z.literal("slack"), target: z.string().url() }),
]);

type SubscriptionFormValues = z.infer<typeof subscriptionFormSchema>;

export function AddSubscriptionForm({ onCreated }: { onCreated?: () => void }) {
  const createSubscription = useCreateStatusSubscription();
  const form = useForm<SubscriptionFormValues>({
    resolver: zodResolver(subscriptionFormSchema),
    defaultValues: {
      channel: "email",
      target: "",
      scope_components: "",
    },
  });
  const channel = form.watch("channel");

  const submit = form.handleSubmit(async (values) => {
    const parsed = channelTargetSchema.safeParse({
      channel: values.channel,
      target: values.target.trim(),
    });
    if (!parsed.success) {
      form.setError("target", {
        message:
          values.channel === "email"
            ? "Enter a valid email address."
            : "Enter a valid webhook URL.",
      });
      return;
    }
    await createSubscription.mutateAsync({
      channel: values.channel,
      target: parsed.data.target,
      scope_components: parseScope(values.scope_components),
    });
    form.reset();
    onCreated?.();
  });

  return (
    <Form {...form}>
      <form className="space-y-4" onSubmit={submit}>
        <div className="grid gap-4 md:grid-cols-[12rem,1fr]">
          <FormField
            control={form.control}
            name="channel"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Channel</FormLabel>
                <FormControl>
                  <Select {...field}>
                    <option value="email">Email</option>
                    <option value="webhook">Webhook</option>
                    <option value="slack">Slack</option>
                  </Select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="target"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{targetLabel(channel)}</FormLabel>
                <FormControl>
                  <Input placeholder={targetPlaceholder(channel)} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        <FormField
          control={form.control}
          name="scope_components"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Component scope</FormLabel>
              <FormControl>
                <Input placeholder="control-plane-api, reasoning-engine" {...field} />
              </FormControl>
              <p className="text-xs text-muted-foreground">
                Leave blank to receive updates for all components.
              </p>
              <FormMessage />
            </FormItem>
          )}
        />
        {channel === "webhook" ? (
          <p className="text-sm text-muted-foreground">
            The backend sends an immediate signed test ping before marking the subscription healthy.
          </p>
        ) : null}
        <div className="flex justify-end">
          <Button disabled={createSubscription.isPending} type="submit">
            Add Subscription
          </Button>
        </div>
      </form>
    </Form>
  );
}

function parseScope(value?: string) {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function targetLabel(channel: SubscriptionFormValues["channel"]) {
  if (channel === "email") {
    return "Email";
  }
  if (channel === "slack") {
    return "Slack webhook URL";
  }
  return "Webhook URL";
}

function targetPlaceholder(channel: SubscriptionFormValues["channel"]) {
  if (channel === "email") {
    return "ops@example.com";
  }
  if (channel === "slack") {
    return "https://hooks.slack.com/services/...";
  }
  return "https://example.com/status-webhook";
}
