"use client";

import { useCallback, useSyncExternalStore } from "react";

type Listener = () => void;

const streamBuffer = new Map<string, string>();
let streamSnapshot = new Map<string, string>();
let animationFrameId: number | null = null;
const listeners = new Set<Listener>();

function notifyListeners() {
  listeners.forEach((listener) => listener());
}

function flushSnapshot() {
  animationFrameId = null;
  streamSnapshot = new Map(streamBuffer);
  notifyListeners();
}

function scheduleFlush() {
  if (animationFrameId !== null) {
    return;
  }

  animationFrameId = window.requestAnimationFrame(flushSnapshot);
}

export function addStreamDelta(messageId: string, delta: string) {
  streamBuffer.set(messageId, `${streamBuffer.get(messageId) ?? ""}${delta}`);
  scheduleFlush();
}

export function clearStream(messageId: string) {
  streamBuffer.delete(messageId);
  scheduleFlush();
}

export function resetStreamState() {
  streamBuffer.clear();
  streamSnapshot = new Map();
  if (animationFrameId !== null) {
    window.cancelAnimationFrame(animationFrameId);
    animationFrameId = null;
  }
  notifyListeners();
}

function subscribe(listener: Listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot() {
  return streamSnapshot;
}

export function useMessageStream() {
  const streamingContent = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const getStreamingContent = useCallback(
    (messageId: string) => streamingContent.get(messageId),
    [streamingContent],
  );

  return {
    addDelta: addStreamDelta,
    clearStream,
    getStreamingContent,
    streamingContent,
  };
}
