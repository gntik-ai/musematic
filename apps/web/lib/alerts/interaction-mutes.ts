"use client";

import type { InteractionAlertMute } from "@/types/alerts";

const STORAGE_PREFIX = "musematic.alert-mutes";

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}:${userId}`;
}

function normalizeInteractionMute(
  value: unknown,
  fallbackUserId: string | null | undefined,
): InteractionAlertMute | null {
  const record = asRecord(value);
  const interactionId = typeof record.interactionId === "string"
    ? record.interactionId
    : typeof record.interaction_id === "string"
      ? record.interaction_id
      : "";

  if (!interactionId) {
    return null;
  }

  const mutedAt = typeof record.mutedAt === "string"
    ? record.mutedAt
    : typeof record.muted_at === "string"
      ? record.muted_at
      : new Date().toISOString();

  const userId = typeof record.userId === "string"
    ? record.userId
    : typeof record.user_id === "string"
      ? record.user_id
      : fallbackUserId ?? "";

  return {
    interactionId,
    mutedAt,
    userId,
  };
}

function dedupeInteractionMutes(mutes: InteractionAlertMute[]): InteractionAlertMute[] {
  const byInteractionId = new Map<string, InteractionAlertMute>();

  for (const mute of mutes) {
    if (!mute.interactionId) {
      continue;
    }
    byInteractionId.set(mute.interactionId, mute);
  }

  return [...byInteractionId.values()].sort((left, right) =>
    left.interactionId.localeCompare(right.interactionId),
  );
}

export function readInteractionAlertMutes(
  userId: string | null | undefined,
): InteractionAlertMute[] {
  if (!userId || typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(storageKey(userId));
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }

    return dedupeInteractionMutes(
      parsed
        .map((item) => normalizeInteractionMute(item, userId))
        .filter((item): item is InteractionAlertMute => item !== null),
    );
  } catch {
    return [];
  }
}

export function writeInteractionAlertMutes(
  userId: string | null | undefined,
  mutes: InteractionAlertMute[],
): void {
  if (!userId || typeof window === "undefined") {
    return;
  }

  const normalized = dedupeInteractionMutes(mutes);
  if (normalized.length === 0) {
    window.localStorage.removeItem(storageKey(userId));
    return;
  }

  window.localStorage.setItem(storageKey(userId), JSON.stringify(normalized));
}

export function normalizeInteractionAlertMutes(
  raw: unknown,
  userId: string | null | undefined,
): InteractionAlertMute[] {
  if (raw === undefined) {
    return readInteractionAlertMutes(userId);
  }

  if (!Array.isArray(raw)) {
    return [];
  }

  const normalized = dedupeInteractionMutes(
    raw
      .map((item) => normalizeInteractionMute(item, userId))
      .filter((item): item is InteractionAlertMute => item !== null),
  );
  writeInteractionAlertMutes(userId, normalized);
  return normalized;
}

export function serializeInteractionAlertMutes(
  mutes: InteractionAlertMute[],
): Array<{ interaction_id: string; muted_at: string }> {
  return dedupeInteractionMutes(mutes).map((mute) => ({
    interaction_id: mute.interactionId,
    muted_at: mute.mutedAt,
  }));
}

export function upsertInteractionAlertMute(
  mutes: InteractionAlertMute[],
  interactionId: string,
  userId: string | null | undefined,
): InteractionAlertMute[] {
  return dedupeInteractionMutes([
    ...mutes.filter((mute) => mute.interactionId !== interactionId),
    {
      interactionId,
      mutedAt: new Date().toISOString(),
      userId: userId ?? "",
    },
  ]);
}

export function removeInteractionAlertMute(
  mutes: InteractionAlertMute[],
  interactionId: string,
): InteractionAlertMute[] {
  return dedupeInteractionMutes(
    mutes.filter((mute) => mute.interactionId !== interactionId),
  );
}

export function isInteractionAlertMuted(
  userId: string | null | undefined,
  interactionId: string | null,
): boolean {
  if (!interactionId) {
    return false;
  }

  return readInteractionAlertMutes(userId).some(
    (mute) => mute.interactionId === interactionId,
  );
}

export function extractAlertInteractionId(payload: unknown): string | null {
  const root = asRecord(payload);
  const alert = asRecord(root.alert);

  const directCandidates = [
    root.interactionId,
    root.interaction_id,
    alert.interactionId,
    alert.interaction_id,
  ];

  for (const candidate of directCandidates) {
    if (typeof candidate === "string" && candidate.length > 0) {
      return candidate;
    }
  }

  const reference = asRecord(
    alert.resourceRef ??
      alert.resource_reference ??
      alert.source_reference ??
      root.resourceRef ??
      root.resource_reference ??
      root.source_reference,
  );
  const kind = typeof reference.kind === "string" ? reference.kind : null;
  const id = typeof reference.id === "string" ? reference.id : null;

  return kind === "interaction" && id ? id : null;
}
