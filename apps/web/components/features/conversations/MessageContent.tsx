"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { JsonViewer } from "@/components/shared/JsonViewer";
import { CodeBlock } from "@/components/features/conversations/CodeBlock";

interface MessageContentProps {
  content: string;
  isStreaming?: boolean;
}

function tryParseJson(value: string) {
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return null;
  }
}

function looksLikeMarkdown(value: string) {
  return /(^#{1,6}\s)|(\*\*)|(```)|(^-\s)|(\|.+\|)/m.test(value);
}

export function MessageContent({
  content,
  isStreaming = false,
}: MessageContentProps) {
  const trimmed = content.trim();
  const parsedJson = trimmed ? tryParseJson(trimmed) : null;

  if (isStreaming) {
    return <p className="whitespace-pre-wrap break-words">{content}</p>;
  }

  if (parsedJson !== null && (trimmed.startsWith("{") || trimmed.startsWith("["))) {
    return <JsonViewer value={parsedJson} />;
  }

  if (!looksLikeMarkdown(content)) {
    return <p className="whitespace-pre-wrap break-words">{content}</p>;
  }

  return (
    <div className="prose prose-sm max-w-none dark:prose-invert prose-pre:bg-transparent prose-pre:p-0">
      <ReactMarkdown
        components={{
          code({ className, children, ...props }) {
            const rawCode = String(children).replace(/\n$/, "");
            const languageMatch = /language-(\w+)/.exec(className ?? "");
            const language = languageMatch?.[1] ?? "text";
            const jsonValue =
              language === "json" ? tryParseJson(rawCode) : null;

            if (jsonValue !== null) {
              return <JsonViewer value={jsonValue} />;
            }

            if (className?.includes("language-")) {
              return <CodeBlock code={rawCode} language={language} />;
            }

            return <code {...props}>{children}</code>;
          },
          table({ children }) {
            return (
              <div className="overflow-x-auto">
                <table>{children}</table>
              </div>
            );
          },
        }}
        remarkPlugins={[remarkGfm]}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
