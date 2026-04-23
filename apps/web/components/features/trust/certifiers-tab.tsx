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
import { Textarea } from "@/components/ui/textarea";
import {
  useCertifierMutations,
  useThirdPartyCertifiers,
} from "@/lib/hooks/use-third-party-certifiers";
import { useAuthStore } from "@/store/auth-store";

const certifierSchema = z.object({
  displayName: z.string().min(1, "Display name is required."),
  endpoint: z
    .string()
    .url("Endpoint must be a valid URL.")
    .refine((value) => value.startsWith("https://"), {
      message: "Endpoint must use HTTPS.",
    }),
  publicKeyPem: z
    .string()
    .min(1, "PEM public key is required.")
    .refine(
      (value) =>
        value.includes("-----BEGIN PUBLIC KEY-----") &&
        value.includes("-----END PUBLIC KEY-----"),
      { message: "PEM header/footer is invalid." },
    ),
  scope: z.string().min(1, "Scope is required."),
});

type CertifierFormValues = z.infer<typeof certifierSchema>;

const ADMIN_ROLES = new Set(["platform_admin", "superadmin"]);
const DEFAULT_PUBLIC_KEY = `-----BEGIN PUBLIC KEY-----

-----END PUBLIC KEY-----`;

export function CertifiersTab() {
  const roles = useAuthStore((state) => state.user?.roles ?? []);
  const canManage = roles.some((role) => ADMIN_ROLES.has(role));
  const { certifiers } = useThirdPartyCertifiers();
  const { createCertifier, deleteCertifier } = useCertifierMutations();
  const form = useForm<CertifierFormValues>({
    resolver: zodResolver(certifierSchema),
    defaultValues: {
      displayName: "",
      endpoint: "https://",
      publicKeyPem: DEFAULT_PUBLIC_KEY,
      scope: "global",
    },
  });

  return (
    <div className="space-y-6">
      <Form {...form}>
        <form
          className="grid gap-4 rounded-2xl border border-border/70 bg-card/80 p-4 lg:grid-cols-2"
          onSubmit={form.handleSubmit(async (values) => {
            await createCertifier.mutateAsync(values);
            form.reset({
              displayName: "",
              endpoint: "https://",
              publicKeyPem: DEFAULT_PUBLIC_KEY,
              scope: "global",
            });
          })}
        >
          <FormField
            control={form.control}
            name="displayName"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Display name</FormLabel>
                <FormControl>
                  <Input disabled={!canManage} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="endpoint"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Endpoint</FormLabel>
                <FormControl>
                  <Input disabled={!canManage} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="scope"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Scope</FormLabel>
                <FormControl>
                  <Select disabled={!canManage} {...field}>
                    <option value="global">Global</option>
                    <option value="workspace">Workspace</option>
                    <option value="regulated">Regulated domains</option>
                  </Select>
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="publicKeyPem"
            render={({ field }) => (
              <FormItem className="lg:col-span-2">
                <FormLabel>PEM public key</FormLabel>
                <FormControl>
                  <Textarea
                    className="min-h-36 font-mono text-xs"
                    disabled={!canManage}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="flex justify-end lg:col-span-2">
            <Button disabled={!canManage || createCertifier.isPending} type="submit">
              Add certifier
            </Button>
          </div>
        </form>
      </Form>

      <div className="space-y-3">
        {certifiers.map((certifier) => (
          <div
            key={certifier.id}
            className="flex flex-col gap-3 rounded-2xl border border-border/70 bg-card/80 p-4 md:flex-row md:items-center md:justify-between"
          >
            <div>
              <p className="font-medium">{certifier.displayName}</p>
              <p className="text-sm text-muted-foreground">{certifier.endpoint}</p>
              <p className="text-xs text-muted-foreground">
                Scope: {certifier.scope.join(", ") || "global"}
              </p>
            </div>
            <Button
              disabled={!canManage || deleteCertifier.isPending}
              variant="outline"
              onClick={() => void deleteCertifier.mutateAsync({ certifierId: certifier.id })}
            >
              Delete
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
