"use client";

import { useCallback, useEffect, useRef } from "react";
import { useConversationStore } from "@/lib/stores/conversation-store";

export function useAutoScroll() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const enableAutoScroll = useConversationStore((state) => state.enableAutoScroll);
  const pauseAutoScroll = useConversationStore((state) => state.pauseAutoScroll);
  const clearPending = useConversationStore((state) => state.clearPending);

  const scrollToBottom = useCallback(() => {
    sentinelRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    enableAutoScroll();
    clearPending();
  }, [clearPending, enableAutoScroll]);

  useEffect(() => {
    if (!sentinelRef.current || typeof IntersectionObserver === "undefined") {
      return undefined;
    }

    const observer = new IntersectionObserver(([entry]) => {
      if (entry?.isIntersecting) {
        enableAutoScroll();
        clearPending();
        return;
      }

      pauseAutoScroll();
    }, {
      root: containerRef.current,
      threshold: 1,
    });

    observer.observe(sentinelRef.current);
    return () => {
      observer.disconnect();
    };
  }, [clearPending, enableAutoScroll, pauseAutoScroll]);

  return {
    containerRef,
    sentinelRef,
    scrollToBottom,
  };
}
