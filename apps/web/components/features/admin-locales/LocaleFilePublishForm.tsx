"use client";

import { useMemo, useState } from "react";
import { Upload } from "lucide-react";
import { localeOptions } from "@/components/features/preferences/LanguagePicker";
import { usePublishLocaleFile } from "@/lib/api/locales";
import { toast } from "@/lib/hooks/use-toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

function countKeys(value: unknown): number {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return 1;
  }
  return Object.values(value).reduce((total, child) => total + countKeys(child), 0);
}

function namespaceCount(value: unknown): number {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return 0;
  }
  return Object.keys(value).length;
}

export function LocaleFilePublishForm() {
  const publishLocaleFile = usePublishLocaleFile();
  const [localeCode, setLocaleCode] = useState("en");
  const [vendorSourceRef, setVendorSourceRef] = useState("");
  const [translationsText, setTranslationsText] = useState("{}");
  const parsedTranslations = useMemo(() => {
    try {
      const parsed = JSON.parse(translationsText) as unknown;
      return parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? (parsed as Record<string, unknown>)
        : null;
    } catch {
      return null;
    }
  }, [translationsText]);

  async function handleFile(file: File | null) {
    if (!file) {
      return;
    }
    setTranslationsText(await file.text());
  }

  async function submit() {
    if (!parsedTranslations) {
      toast({
        title: "Invalid translations JSON",
        description: "Upload or paste a JSON object.",
        variant: "destructive",
      });
      return;
    }

    try {
      await publishLocaleFile.mutateAsync({
        locale_code: localeCode,
        translations: parsedTranslations,
        vendor_source_ref: vendorSourceRef || null,
      });
      toast({ title: "Locale file published", variant: "success" });
    } catch (error) {
      toast({
        title: "Locale file was not published",
        description: error instanceof Error ? error.message : "Another publish may be in progress.",
        variant: "destructive",
      });
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="locale-code">Locale</Label>
          <Select id="locale-code" value={localeCode} onChange={(event) => setLocaleCode(event.target.value)}>
            {localeOptions.map((locale) => (
              <option key={locale.value} value={locale.value}>
                {locale.label}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="vendor-source-ref">Vendor source reference</Label>
          <Input
            id="vendor-source-ref"
            value={vendorSourceRef}
            onChange={(event) => setVendorSourceRef(event.target.value)}
          />
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="translations-file">Upload translations JSON</Label>
        <Input
          id="translations-file"
          type="file"
          accept="application/json,.json"
          onChange={(event) => {
            void handleFile(event.target.files?.[0] ?? null);
          }}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="translations-json">Translations JSON</Label>
        <Textarea
          id="translations-json"
          className="min-h-48 font-mono text-xs"
          value={translationsText}
          onChange={(event) => setTranslationsText(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground" data-testid="locale-json-preview">
          {parsedTranslations
            ? `${namespaceCount(parsedTranslations)} namespaces, ${countKeys(parsedTranslations)} keys`
            : "Invalid JSON"}
        </p>
        <Button
          disabled={publishLocaleFile.isPending || !parsedTranslations}
          disabledByMaintenance
          onClick={() => void submit()}
        >
          <Upload className="h-4 w-4" />
          {publishLocaleFile.isPending ? "Publishing..." : "Publish locale file"}
        </Button>
      </div>
    </div>
  );
}
