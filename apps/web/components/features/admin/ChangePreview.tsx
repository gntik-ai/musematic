import { Clock, GitCompareArrows } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface ChangePreviewProps {
  affectedCount: number;
  irreversibility: "reversible" | "partially_reversible" | "irreversible";
  estimatedDuration: string;
  implications?: string[];
}

const labels = {
  reversible: "Reversible",
  partially_reversible: "Partially reversible",
  irreversible: "Irreversible",
} as const;

export function ChangePreview({
  affectedCount,
  irreversibility,
  estimatedDuration,
  implications = [],
}: ChangePreviewProps) {
  return (
    <div className="grid gap-3 rounded-md border bg-card p-4 md:grid-cols-3">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium">
          <GitCompareArrows className="h-4 w-4" />
          {affectedCount} affected
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{labels[irreversibility]}</p>
      </div>
      <div>
        <div className="flex items-center gap-2 text-sm font-medium">
          <Clock className="h-4 w-4" />
          {estimatedDuration}
        </div>
        <p className="mt-1 text-sm text-muted-foreground">Estimated duration</p>
      </div>
      <div className="flex flex-wrap items-start gap-2">
        {implications.length > 0 ? (
          implications.map((item) => (
            <Badge key={item} variant="outline" className="rounded-md">
              {item}
            </Badge>
          ))
        ) : (
          <Badge variant="secondary" className="rounded-md">
            No cascade
          </Badge>
        )}
      </div>
    </div>
  );
}
