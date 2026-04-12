"use client";

import { useEffect } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useConversationStore } from "@/lib/stores/conversation-store";
import { useAutoScroll } from "@/lib/hooks/use-auto-scroll";
import { MessageBubble } from "@/components/features/conversations/MessageBubble";
import { NewMessagesPill } from "@/components/features/conversations/NewMessagesPill";
import { TypingIndicator } from "@/components/features/conversations/TypingIndicator";
import type { Message } from "@/types/conversations";

interface MessageListProps {
  messages: Message[];
  getStreamingContent: (messageId: string) => string | undefined;
  branchOriginMessageIds?: Set<string>;
  onBranchFromMessage?: (messageId: string) => void;
}

export function MessageList({
  branchOriginMessageIds,
  messages,
  getStreamingContent,
  onBranchFromMessage,
}: MessageListProps) {
  const { containerRef, sentinelRef, scrollToBottom } = useAutoScroll();
  const isAgentProcessing = useConversationStore((state) => state.isAgentProcessing);
  const pendingMessageCount = useConversationStore((state) => state.pendingMessageCount);
  const autoScrollEnabled = useConversationStore((state) => state.autoScrollEnabled);

  const rowVirtualizer = useVirtualizer({
    count: messages.length,
    estimateSize: () => 100,
    getScrollElement: () => containerRef.current,
    overscan: 8,
  });

  useEffect(() => {
    if (autoScrollEnabled) {
      scrollToBottom();
    }
  }, [autoScrollEnabled, messages.length, scrollToBottom]);

  return (
    <div className="relative min-h-0 flex-1">
      <div
        aria-label="Conversation messages"
        aria-live="polite"
        className="h-[calc(100vh-18rem)] overflow-auto pr-2"
        ref={containerRef}
        role="log"
      >
        <div
          className="relative w-full"
          style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
        >
          {rowVirtualizer.getVirtualItems().map((virtualItem) => {
            const message = messages[virtualItem.index];
            if (!message) {
              return null;
            }

            const streamingContent = getStreamingContent(message.id);
            const isStreaming = Boolean(streamingContent);

            return (
              <div
                data-index={virtualItem.index}
                key={virtualItem.key}
                ref={rowVirtualizer.measureElement}
                style={{
                  position: "absolute",
                  top: 0,
                  transform: `translateY(${virtualItem.start}px)`,
                  width: "100%",
                }}
              >
                <div className="pb-4">
                  <MessageBubble
                    isStreaming={isStreaming}
                    message={message}
                    onBranchFrom={
                      onBranchFromMessage
                        ? () => onBranchFromMessage(message.id)
                        : undefined
                    }
                    showBranchOriginIndicator={Boolean(
                      branchOriginMessageIds?.has(message.id),
                    )}
                    streamingContent={streamingContent}
                  />
                </div>
              </div>
            );
          })}
        </div>
        {isAgentProcessing ? (
          <div className="mt-4 flex justify-start">
            <TypingIndicator />
          </div>
        ) : null}
        <div ref={sentinelRef} />
      </div>
      <NewMessagesPill count={pendingMessageCount} onClick={scrollToBottom} />
    </div>
  );
}
