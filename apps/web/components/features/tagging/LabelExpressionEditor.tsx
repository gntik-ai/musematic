"use client";

import Editor from "@monaco-editor/react";
import { Badge } from "@/components/ui/badge";
import { useLabelExpressionValidate } from "@/lib/api/tagging";
import { AlertCircle, Check } from "lucide-react";
import { useEffect, useState } from "react";

interface LabelExpressionEditorProps {
  value: string;
  onChange: (value: string) => void;
}

export function LabelExpressionEditor({ value, onChange }: LabelExpressionEditorProps) {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(value), 300);
    return () => window.clearTimeout(handle);
  }, [value]);

  const validation = useLabelExpressionValidate(debounced);
  const result = validation.data;

  return (
    <div className="space-y-2">
      <Editor
        height="120px"
        language="text"
        onChange={(next) => onChange(next ?? "")}
        options={{
          minimap: { enabled: false },
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          wordWrap: "on",
        }}
        value={value}
      />
      {result?.valid ? (
        <Badge className="gap-1" variant="outline">
          <Check className="h-3.5 w-3.5" aria-hidden="true" />
          Valid
        </Badge>
      ) : result?.error ? (
        <Badge className="gap-1" variant="destructive">
          <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
          {result.error.line}:{result.error.col} {result.error.message}
        </Badge>
      ) : null}
    </div>
  );
}
