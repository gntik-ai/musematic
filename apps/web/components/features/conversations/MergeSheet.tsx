"use client";

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import { MessageBubble } from "@/components/features/conversations/MessageBubble";
import { useMergeBranch } from "@/lib/hooks/use-branch";
import type { ConversationBranch, Message } from "@/types/conversations";

interface MergeSheetProps {
  branch: ConversationBranch | null;
  conversationId: string;
  messages: Message[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function MergeSheet({
  branch,
  conversationId,
  messages,
  onOpenChange,
  open,
}: MergeSheetProps) {
  const mergeBranch = useMergeBranch();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const isDisabled = useMemo(
    () => selectedIds.length === 0 || !branch,
    [branch, selectedIds.length],
  );

  return (
    <Sheet onOpenChange={onOpenChange} open={open}>
      <SheetContent className="ml-auto max-w-2xl">
        <SheetTitle>Merge branch</SheetTitle>
        <SheetDescription>
          Select the branch messages to merge back into the main thread.
        </SheetDescription>
        <div className="mt-6 space-y-4">
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              This branch does not contain any messages yet.
            </p>
          ) : (
            messages.map((message) => {
              const isSelected = selectedIds.includes(message.id);

              return (
                <label
                  className="flex items-start gap-3 rounded-xl border border-border p-3"
                  key={message.id}
                >
                  <Checkbox
                    aria-label={`Select message ${message.id} for merge`}
                    checked={isSelected}
                    onChange={(event) => {
                      setSelectedIds((current) =>
                        event.target.checked
                          ? [...current, message.id]
                          : current.filter((id) => id !== message.id),
                      );
                    }}
                  />
                  <div className="min-w-0 flex-1">
                    <MessageBubble message={message} />
                  </div>
                </label>
              );
            })
          )}
        </div>
        <div className="mt-6 flex justify-end">
          <Button
            aria-label="Merge selected messages into main thread"
            disabled={isDisabled}
            onClick={async () => {
              if (!branch) {
                return;
              }

              await mergeBranch.mutateAsync({
                branchId: branch.id,
                conversationId,
                message_ids: selectedIds,
              });
              setSelectedIds([]);
              onOpenChange(false);
            }}
          >
            Merge selected
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
