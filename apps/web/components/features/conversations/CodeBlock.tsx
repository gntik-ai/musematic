"use client";

import { useEffect, useMemo, useState } from "react";
import { Check, ChevronDown, ChevronUp, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ConversationCodeBlockProps {
  code: string;
  language?: string;
}

export function CodeBlock({
  code,
  language = "text",
}: ConversationCodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const [highlightedHtml, setHighlightedHtml] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const lines = useMemo(() => code.split("\n"), [code]);
  const isCollapsible = lines.length > 40;
  const visibleCode = useMemo(() => {
    if (expanded || !isCollapsible) {
      return code;
    }

    return lines.slice(0, 10).join("\n");
  }, [code, expanded, isCollapsible, lines]);

  useEffect(() => {
    let active = true;

    void (async () => {
      try {
        const hljs = (await import("highlight.js/lib/core")).default;
        const json = (await import("highlight.js/lib/languages/json")).default;
        const bash = (await import("highlight.js/lib/languages/bash")).default;
        const python = (await import("highlight.js/lib/languages/python")).default;
        const typescript = (await import("highlight.js/lib/languages/typescript")).default;

        hljs.registerLanguage("json", json);
        hljs.registerLanguage("bash", bash);
        hljs.registerLanguage("python", python);
        hljs.registerLanguage("typescript", typescript);

        const safeLanguage = ["json", "bash", "python", "typescript"].includes(language)
          ? language
          : "typescript";

        const result = hljs.highlight(visibleCode, { language: safeLanguage }).value;
        if (active) {
          setHighlightedHtml(result);
        }
      } catch {
        if (active) {
          setHighlightedHtml(null);
        }
      }
    })();

    return () => {
      active = false;
    };
  }, [language, visibleCode]);

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-muted/60">
      <div className="flex items-center justify-between border-b border-border/70 px-4 py-2">
        <span className="font-mono text-xs uppercase tracking-[0.16em] text-muted-foreground">
          {language}
        </span>
        <div className="flex items-center gap-2">
          {isCollapsible ? (
            <Button
              onClick={() => setExpanded((value) => !value)}
              size="sm"
              type="button"
              variant="ghost"
            >
              {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              {expanded ? "Show less" : `Show all ${lines.length} lines`}
            </Button>
          ) : null}
          <Button
            aria-label="Copy code block"
            onClick={async () => {
              await navigator.clipboard.writeText(code);
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1500);
            }}
            size="sm"
            type="button"
            variant="ghost"
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copied ? "Copied!" : "Copy"}
          </Button>
        </div>
      </div>
      <pre className="overflow-x-auto p-4 text-sm">
        {highlightedHtml ? (
          <code dangerouslySetInnerHTML={{ __html: highlightedHtml }} />
        ) : (
          <code>{visibleCode}</code>
        )}
      </pre>
    </div>
  );
}
