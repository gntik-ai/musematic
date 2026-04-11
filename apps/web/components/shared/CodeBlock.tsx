"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

export function CodeBlock({
  code,
  language = "typescript",
  maxHeight,
}: {
  code: string;
  language?: string;
  maxHeight?: number;
}) {
  const [copied, setCopied] = useState(false);
  const [html, setHtml] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const hljs = (await import("highlight.js/lib/core")).default;
        const ts = (await import("highlight.js/lib/languages/typescript")).default;
        const json = (await import("highlight.js/lib/languages/json")).default;
        const bash = (await import("highlight.js/lib/languages/bash")).default;
        const safeLanguage = ["typescript", "json", "bash"].includes(language) ? language : "typescript";
        hljs.registerLanguage("typescript", ts);
        hljs.registerLanguage("json", json);
        hljs.registerLanguage("bash", bash);
        const highlighted = hljs.highlight(code, { language: safeLanguage }).value;
        if (active) {
          setHtml(highlighted);
        }
      } catch {
        if (active) {
          setHtml(null);
        }
      }
    })();

    return () => {
      active = false;
    };
  }, [code, language]);

  const content = useMemo(() => {
    if (html) {
      return <code dangerouslySetInnerHTML={{ __html: html }} />;
    }
    return <code>{code}</code>;
  }, [code, html]);

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-muted/60">
      <div className="flex items-center justify-between border-b border-border/80 px-4 py-2">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-muted-foreground">{language}</span>
        <Button
          size="sm"
          variant="ghost"
          onClick={async () => {
            await navigator.clipboard.writeText(code);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 2000);
          }}
        >
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          Copy
        </Button>
      </div>
      <pre className="overflow-x-auto p-4 text-sm" style={maxHeight ? { maxHeight } : undefined}>
        {content}
      </pre>
    </div>
  );
}
