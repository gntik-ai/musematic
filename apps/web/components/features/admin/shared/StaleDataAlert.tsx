import { AlertTriangle, RefreshCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function StaleDataAlert({ onReload }: { onReload: () => void }) {
  return (
    <Alert className="border-amber-500/30 bg-amber-500/10">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div>
            <AlertTitle>Stale settings detected</AlertTitle>
            <AlertDescription>
              Settings were changed by another administrator. Reload to see the
              latest values.
            </AlertDescription>
          </div>
        </div>
        <Button className="shrink-0" size="sm" variant="outline" onClick={onReload}>
          <RefreshCcw className="h-4 w-4" />
          Reload
        </Button>
      </div>
    </Alert>
  );
}
