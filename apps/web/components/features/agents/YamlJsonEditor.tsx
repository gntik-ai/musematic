"use client";

import dynamic from "next/dynamic";
import { useCallback, useMemo, useState } from "react";
import type { BeforeMount, OnChange } from "@monaco-editor/react";
import { FileJson, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const MonacoEditor = dynamic(
  async () => {
    const module = await import("@monaco-editor/react");
    return module.Editor;
  },
  {
    ssr: false,
    loading: () => <Skeleton className="h-[520px] w-full rounded-lg" />,
  },
);

export interface YamlJsonEditorProps {
  value: string;
  onChange: (value: string) => void;
  schema?: Record<string, unknown> | undefined;
  defaultLanguage?: "yaml" | "json" | undefined;
  enableLanguageToggle?: boolean | undefined;
  label: string;
  className?: string;
}

export function YamlJsonEditor({
  value,
  onChange,
  schema,
  defaultLanguage = "json",
  enableLanguageToggle = false,
  label,
  className,
}: YamlJsonEditorProps) {
  const [language, setLanguage] = useState<"yaml" | "json">(defaultLanguage);
  const path = useMemo(
    () => `inmemory://creator-ui/${label.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.${language}`,
    [label, language],
  );

  const beforeMount = useCallback<BeforeMount>(
    (monaco) => {
      if (!schema) {
        return;
      }
      monaco.languages.json.jsonDefaults.setDiagnosticsOptions({
        validate: true,
        allowComments: false,
        schemas: [
          {
            uri: `inmemory://creator-ui/${label}.schema.json`,
            fileMatch: [path],
            schema,
          },
        ],
      });
    },
    [label, path, schema],
  );

  const handleChange = useCallback<OnChange>(
    (nextValue) => {
      onChange(nextValue ?? "");
    },
    [onChange],
  );

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{label}</p>
          <p className="text-xs text-muted-foreground">
            {schema ? "Schema validation enabled" : "Schema loading"}
          </p>
        </div>
        {enableLanguageToggle ? (
          <div className="flex rounded-md border border-border bg-background p-1">
            <Button
              aria-pressed={language === "yaml"}
              size="sm"
              type="button"
              variant={language === "yaml" ? "secondary" : "ghost"}
              onClick={() => setLanguage("yaml")}
            >
              <FileText className="h-4 w-4" />
              YAML
            </Button>
            <Button
              aria-pressed={language === "json"}
              size="sm"
              type="button"
              variant={language === "json" ? "secondary" : "ghost"}
              onClick={() => setLanguage("json")}
            >
              <FileJson className="h-4 w-4" />
              JSON
            </Button>
          </div>
        ) : null}
      </div>
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <MonacoEditor
          beforeMount={beforeMount}
          height="520px"
          language={language}
          onChange={handleChange}
          options={{
            automaticLayout: true,
            fontFamily: "var(--font-mono)",
            fontSize: 13,
            minimap: { enabled: false },
            padding: { top: 14 },
            scrollBeyondLastLine: false,
            tabSize: 2,
            wordWrap: "on",
          }}
          path={path}
          theme="vs-dark"
          value={value}
        />
      </div>
    </div>
  );
}
