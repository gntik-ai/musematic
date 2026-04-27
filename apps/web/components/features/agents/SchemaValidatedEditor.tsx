"use client";

import { AlertTriangle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { YamlJsonEditor } from "@/components/features/agents/YamlJsonEditor";

interface SchemaValidatedEditorProps {
  value: string;
  onChange: (value: string) => void;
  schema?: Record<string, unknown> | undefined;
  isSchemaLoading?: boolean;
  label: string;
  defaultLanguage?: "yaml" | "json";
  enableLanguageToggle?: boolean;
}

export function SchemaValidatedEditor({
  value,
  onChange,
  schema,
  isSchemaLoading = false,
  label,
  defaultLanguage,
  enableLanguageToggle,
}: SchemaValidatedEditorProps) {
  return (
    <div className="space-y-3">
      {!schema && !isSchemaLoading ? (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Schema unavailable</AlertTitle>
          <AlertDescription>Inline validation is unavailable for this editor.</AlertDescription>
        </Alert>
      ) : null}
      <YamlJsonEditor
        defaultLanguage={defaultLanguage}
        enableLanguageToggle={enableLanguageToggle}
        label={label}
        schema={schema}
        value={value}
        onChange={onChange}
      />
    </div>
  );
}
