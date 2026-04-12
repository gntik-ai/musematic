"use client";

import Link from "next/link";
import { MessageContent } from "@/components/features/conversations/MessageContent";
import type { GoalMessage } from "@/types/conversations";

export function GoalMessageBubble({
  message,
}: {
  message: GoalMessage;
}) {
  const alignmentClassName =
    message.sender_type === "user"
      ? "flex justify-end"
      : message.sender_type === "system"
        ? "flex justify-center"
        : "flex justify-start";

  const bubbleClassName =
    message.sender_type === "user"
      ? "bg-primary text-primary-foreground"
      : message.sender_type === "system"
        ? "bg-transparent text-muted-foreground italic"
        : "bg-muted text-foreground";

  return (
    <article className={alignmentClassName}>
      <div className="max-w-3xl space-y-2">
        <div className={`rounded-2xl px-4 py-3 text-sm shadow-sm ${bubbleClassName}`}>
          <MessageContent content={message.content} />
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {message.agent_fqn ? <span>{message.agent_fqn}</span> : null}
          {message.originating_interaction_id ? (
            <Link
              className="underline underline-offset-4"
              href={`/conversations/${message.originating_interaction_id}`}
            >
              ↗ view interaction
            </Link>
          ) : null}
        </div>
      </div>
    </article>
  );
}
