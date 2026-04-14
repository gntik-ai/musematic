"use client";

import dynamic from "next/dynamic";
import { useTheme } from "next-themes";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
import { configureMonacoYaml, type MonacoYaml } from "monaco-yaml";
import type {
  BeforeMount,
  Monaco,
  OnValidate,
} from "@monaco-editor/react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useWorkflowSchema } from "@/lib/hooks/use-workflow-schema";
import { useWorkflowEditorStore } from "@/lib/stores/workflow-editor-store";
import type { ValidationError, WorkflowSchema } from "@/types/workflows";

const MonacoEditor = dynamic(
  async () => {
    const module = await import("@monaco-editor/react");
    return module.Editor;
  },
  {
    ssr: false,
    loading: () => (
      <div className="flex h-full min-h-[420px] flex-col gap-3 rounded-2xl border border-border/60 bg-card/80 p-6">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-full min-h-[320px] rounded-xl" />
      </div>
    ),
  },
);

const MODEL_PATH = "inmemory://workflow-editor/workflow.yaml";
const SCHEMA_URI = "inmemory://workflow-editor/schema.json";

interface MonacoYamlEditorProps {
  initialValue?: string;
  initialVersionId?: string | null;
  className?: string;
}

function normalizeValidationErrors(
  markers: Parameters<OnValidate>[0],
  monaco: Monaco | null,
): ValidationError[] {
  const errorSeverity = monaco?.MarkerSeverity.Error ?? 8;

  return markers.map((marker) => ({
    line: marker.startLineNumber,
    column: marker.startColumn,
    message: marker.message,
    severity: marker.severity === errorSeverity ? "error" : "warning",
    path:
      typeof marker.code === "string"
        ? marker.code
        : marker.source ?? marker.code?.value ?? "",
  }));
}

function configureYamlLanguage(
  monaco: Monaco,
  schema: WorkflowSchema | undefined,
  handleRef: MutableRefObject<MonacoYaml | null>,
) {
  const options = {
    enableSchemaRequest: false,
    validate: true,
    completion: true,
    hover: true,
    format: true,
    yamlVersion: "1.2" as const,
    schemas: schema
      ? [
          {
            uri: SCHEMA_URI,
            fileMatch: [MODEL_PATH, "**/*.yaml", "**/*.yml"],
            schema,
          },
        ]
      : [],
  };

  if (handleRef.current) {
    void handleRef.current.update(options);
    return;
  }

  handleRef.current = configureMonacoYaml(monaco, options);
}

export function MonacoYamlEditor({
  initialValue = "",
  initialVersionId = null,
  className,
}: MonacoYamlEditorProps) {
  const { data: schema, error: schemaError } = useWorkflowSchema();
  const { resolvedTheme } = useTheme();
  const validationErrorsCount = useWorkflowEditorStore(
    (state) => state.validationErrors.length,
  );
  const setYamlContent = useWorkflowEditorStore((state) => state.setYamlContent);
  const setValidationErrors = useWorkflowEditorStore(
    (state) => state.setValidationErrors,
  );

  const [editorValue, setEditorValue] = useState(initialValue);
  const monacoRef = useRef<Monaco | null>(null);
  const monacoYamlRef = useRef<MonacoYaml | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seedKeyRef = useRef<string | null>(null);

  const editorTheme = useMemo(() => {
    if (typeof document !== "undefined") {
      return document.documentElement.classList.contains("dark") ? "vs-dark" : "light";
    }

    return resolvedTheme === "dark" ? "vs-dark" : "light";
  }, [resolvedTheme]);

  useEffect(() => {
    const seedKey = `${initialVersionId ?? "new"}:${initialValue}`;
    if (seedKeyRef.current === seedKey) {
      return;
    }

    seedKeyRef.current = seedKey;
    setEditorValue(initialValue);
    useWorkflowEditorStore.setState((state) => ({
      ...state,
      yamlContent: initialValue,
      validationErrors: [],
      graphNodes: [],
      graphEdges: [],
      parseError: null,
      isDirty: false,
      isSaving: false,
      lastSavedVersionId: initialVersionId ?? state.lastSavedVersionId,
    }));
  }, [initialValue, initialVersionId]);

  useEffect(() => {
    if (!monacoRef.current) {
      return;
    }

    configureYamlLanguage(monacoRef.current, schema, monacoYamlRef);
  }, [schema]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }

      monacoYamlRef.current?.dispose();
      monacoYamlRef.current = null;
    };
  }, []);

  const beforeMount = useCallback<BeforeMount>(
    (monaco) => {
      monacoRef.current = monaco;
      configureYamlLanguage(monaco, schema, monacoYamlRef);
    },
    [schema],
  );

  const handleChange = useCallback(
    (value: string | undefined) => {
      const nextValue = value ?? "";
      setEditorValue(nextValue);

      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }

      debounceRef.current = setTimeout(() => {
        setYamlContent(nextValue);
      }, 500);
    },
    [setYamlContent],
  );

  const handleValidate = useCallback<OnValidate>(
    (markers) => {
      setValidationErrors(normalizeValidationErrors(markers, monacoRef.current));
    },
    [setValidationErrors],
  );

  return (
    <div className={cn("flex h-full flex-col gap-3", className)}>
      {schemaError ? (
        <Alert variant="destructive">
          <AlertTitle>Schema unavailable</AlertTitle>
          <AlertDescription>
            The workflow schema could not be loaded. YAML syntax still works, but
            inline validation will be incomplete.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="rounded-2xl border border-border/60 bg-card/80 shadow-sm">
        <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
          <div>
            <p className="text-sm font-medium text-foreground">Workflow YAML</p>
            <p className="text-xs text-muted-foreground">
              Validation updates after you stop typing for 500ms.
            </p>
          </div>
          <span className="text-xs text-muted-foreground">
            {editorValue.length > 0
              ? `${editorValue.split(/\r?\n/).length} lines`
              : "Ready"}
            {validationErrorsCount > 0
              ? ` • ${validationErrorsCount} diagnostic${validationErrorsCount === 1 ? "" : "s"}`
              : ""}
          </span>
        </div>

        <div className="h-[560px]">
          <MonacoEditor
            beforeMount={beforeMount}
            className="overflow-hidden rounded-b-2xl"
            defaultLanguage="yaml"
            height="100%"
            keepCurrentModel
            language="yaml"
            onChange={handleChange}
            onValidate={handleValidate}
            options={{
              automaticLayout: true,
              fontFamily: "var(--font-mono)",
              fontSize: 13,
              formatOnPaste: true,
              lineNumbersMinChars: 3,
              minimap: { enabled: false },
              padding: { top: 16 },
              scrollBeyondLastLine: false,
              smoothScrolling: true,
              tabSize: 2,
              wordWrap: "on",
            }}
            path={MODEL_PATH}
            theme={editorTheme}
            value={editorValue}
          />
        </div>
      </div>
    </div>
  );
}
