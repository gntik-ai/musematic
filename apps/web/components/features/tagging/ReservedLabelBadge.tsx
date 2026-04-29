"use client";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Lock } from "lucide-react";

export function ReservedLabelBadge() {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <Badge className="gap-1" variant="outline">
            <Lock className="h-3 w-3" aria-hidden="true" />
            Reserved
          </Badge>
        </TooltipTrigger>
        <TooltipContent>Editable by superadmins and service accounts only.</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
