"use client";

import { useEffect, useId, useRef, useState } from "react";
import { SendHorizonal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useSendMessage } from "@/lib/hooks/use-send-message";

interface MessageInputProps {
  conversationId: string;
  interactionId: string;
  isAgentProcessing: boolean;
}

export function MessageInput({
  conversationId,
  interactionId,
  isAgentProcessing,
}: MessageInputProps) {
  const [content, setContent] = useState("");
  const hintId = useId();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const sendMessage = useSendMessage();

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }

    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [content]);

  return (
    <div className="space-y-3 rounded-2xl border border-border bg-card p-4">
      {isAgentProcessing ? (
        <div className="rounded-xl bg-amber-100 px-3 py-2 text-sm text-amber-800 dark:bg-amber-900 dark:text-amber-200">
          Agent is processing — your message will be delivered as guidance
        </div>
      ) : null}
      <Textarea
        aria-describedby={hintId}
        aria-label="Type a message"
        onChange={(event) => setContent(event.target.value)}
        onKeyDown={async (event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && content.trim()) {
            event.preventDefault();
            await sendMessage.mutateAsync({
              content: content.trim(),
              conversationId,
              interactionId,
            });
            setContent("");
          }
        }}
        placeholder={
          isAgentProcessing
            ? "Add guidance while the agent is working…"
            : "Type your message…"
        }
        ref={textareaRef}
        value={content}
      />
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground" id={hintId}>
          Press Ctrl/Cmd+Enter to send
        </p>
        <Button
          aria-label="Send message"
          disabled={!content.trim()}
          onClick={async () => {
            await sendMessage.mutateAsync({
              content: content.trim(),
              conversationId,
              interactionId,
            });
            setContent("");
          }}
          variant={isAgentProcessing ? "secondary" : "default"}
        >
          <SendHorizonal className="h-4 w-4" />
          Send
        </Button>
      </div>
    </div>
  );
}
