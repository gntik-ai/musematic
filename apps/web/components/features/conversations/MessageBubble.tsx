"use client";

import { useMemo, useState } from "react";
import { Bot, MoreHorizontal, User2 } from "lucide-react";
import { AttachmentCard } from "@/components/features/conversations/AttachmentCard";
import { BranchOriginIndicator } from "@/components/features/conversations/BranchOriginIndicator";
import { MessageContent } from "@/components/features/conversations/MessageContent";
import { MidProcessBadge } from "@/components/features/conversations/MidProcessBadge";
import { MergedFromBadge } from "@/components/features/conversations/MergedFromBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Message } from "@/types/conversations";

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean | undefined;
  streamingContent?: string | undefined;
  showBranchOrigin?: boolean | undefined;
  showBranchOriginIndicator?: boolean | undefined;
  onBranchFrom?: (() => void) | undefined;
  children?: React.ReactNode | undefined;
}

const MAX_CONTENT_LENGTH = 50_000;

export function MessageBubble({
  message,
  isStreaming = false,
  streamingContent,
  showBranchOrigin = true,
  showBranchOriginIndicator = false,
  onBranchFrom,
  children,
}: MessageBubbleProps) {
  const [expanded, setExpanded] = useState(false);
  const resolvedContent = streamingContent ?? message.content;

  const { alignmentClassName, bubbleClassName, icon, label } = useMemo(() => {
    switch (message.sender_type) {
      case "user":
        return {
          alignmentClassName: "flex justify-end",
          bubbleClassName: "bg-primary text-primary-foreground",
          icon: <User2 className="h-4 w-4" />,
          label: message.sender_display_name || "User",
        };
      case "system":
        return {
          alignmentClassName: "flex justify-center",
          bubbleClassName: "bg-transparent text-center italic text-muted-foreground",
          icon: null,
          label: "System",
        };
      default:
        return {
          alignmentClassName: "flex justify-start",
          bubbleClassName: "bg-muted text-foreground",
          icon: <Bot className="h-4 w-4" />,
          label: message.sender_display_name || "Agent",
        };
    }
  }, [message.sender_display_name, message.sender_type]);

  const isTruncated = resolvedContent.length > MAX_CONTENT_LENGTH;
  const displayedContent =
    expanded || !isTruncated
      ? resolvedContent
      : `${resolvedContent.slice(0, MAX_CONTENT_LENGTH)}…`;

  return (
    <article
      aria-label={`${label} message`}
      className={alignmentClassName}
      data-message-id={message.id}
    >
      <div className="max-w-3xl space-y-2">
        <div className="flex items-center justify-between gap-3">
          {message.sender_type === "agent" ? (
            <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
              {icon}
              <span>{message.sender_display_name}</span>
              {showBranchOriginIndicator ? <BranchOriginIndicator /> : null}
            </div>
          ) : showBranchOriginIndicator ? (
            <BranchOriginIndicator />
          ) : (
            <span />
          )}
          {onBranchFrom ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  aria-label="Message actions"
                  size="icon"
                  variant="ghost"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  aria-label="Branch from this message"
                  onClick={onBranchFrom}
                >
                  Branch from here
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null}
        </div>
        <div className={`rounded-2xl px-4 py-3 text-sm shadow-sm ${bubbleClassName}`}>
          {children ? (
            children
          ) : (
            <MessageContent
              content={displayedContent}
              isStreaming={isStreaming}
            />
          )}
          {isStreaming ? (
            <span className="ml-1 inline-block h-4 w-2 animate-pulse rounded-sm bg-current align-middle" />
          ) : null}
        </div>
        {message.attachments.length > 0 ? (
          <div className="grid gap-3">
            {message.attachments.map((attachment) => (
              <AttachmentCard attachment={attachment} key={attachment.id} />
            ))}
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {message.is_mid_process_injection ? <MidProcessBadge /> : null}
          {showBranchOrigin && message.branch_origin ? (
            <MergedFromBadge branchName={message.branch_origin} />
          ) : null}
          {isTruncated ? (
            <button
              className="underline underline-offset-4"
              onClick={() => setExpanded((value) => !value)}
              type="button"
            >
              {expanded ? "show less" : "show more"}
            </button>
          ) : null}
        </div>
      </div>
    </article>
  );
}
