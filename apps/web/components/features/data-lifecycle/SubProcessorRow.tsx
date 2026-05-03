"use client";

import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import type { SubProcessor } from "@/lib/api/data-lifecycle";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  useDeleteSubProcessor,
  useUpdateSubProcessor,
} from "@/lib/hooks/use-data-lifecycle";

export function SubProcessorRow({ item }: { item: SubProcessor }) {
  const update = useUpdateSubProcessor();
  const remove = useDeleteSubProcessor();
  const [isActive, setIsActive] = useState(item.is_active);

  const handleToggleActive = (next: boolean) => {
    setIsActive(next);
    update.mutate({ id: item.id, body: { is_active: next } });
  };

  return (
    <tr className="border-t">
      <td className="px-4 py-3 font-medium">{item.name}</td>
      <td className="px-4 py-3 text-muted-foreground">{item.category}</td>
      <td className="px-4 py-3 text-muted-foreground">{item.location}</td>
      <td className="px-4 py-3 text-xs text-muted-foreground">
        {item.data_categories.join(", ")}
      </td>
      <td className="px-4 py-3">
        <Switch checked={isActive} onCheckedChange={handleToggleActive} />
      </td>
      <td className="px-4 py-3 text-right">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            if (confirm(`Remove ${item.name}?`)) {
              remove.mutate(item.id);
            }
          }}
          disabled={remove.isPending}
        >
          {remove.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
        </Button>
      </td>
    </tr>
  );
}
