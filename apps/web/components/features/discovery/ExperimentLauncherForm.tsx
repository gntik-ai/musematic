"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
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
import { Textarea } from "@/components/ui/textarea";
import { useLaunchDiscoveryExperiment } from "@/lib/hooks/use-discovery-session";

const experimentLauncherSchema = z.object({
  notes: z.string().optional(),
});

export function ExperimentLauncherForm({
  hypothesisId,
  workspaceId,
}: {
  hypothesisId: string;
  workspaceId: string;
}) {
  const router = useRouter();
  const launchExperiment = useLaunchDiscoveryExperiment(hypothesisId, workspaceId);
  const form = useForm<z.infer<typeof experimentLauncherSchema>>({
    resolver: zodResolver(experimentLauncherSchema),
    defaultValues: { notes: "" },
  });

  return (
    <Form {...form}>
      <form
        className="space-y-4 rounded-lg border border-border bg-card p-4"
        onSubmit={form.handleSubmit(async () => {
          const experiment = await launchExperiment.mutateAsync({});
          router.push(`/discovery/${encodeURIComponent(experiment.session_id)}/experiments`);
        })}
      >
        <FormField
          control={form.control}
          name="notes"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Experiment notes</FormLabel>
              <FormControl>
                <Textarea placeholder="Optional local planning notes" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="flex justify-end">
          <Button disabled={launchExperiment.isPending} type="submit">
            Launch Experiment
          </Button>
        </div>
      </form>
    </Form>
  );
}
