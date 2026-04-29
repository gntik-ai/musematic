"use client";

import { HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

interface AdminHelpProps {
  children: React.ReactNode;
}

export function AdminHelp({ children }: AdminHelpProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm">
          <HelpCircle className="h-4 w-4" />
          Help
        </Button>
      </PopoverTrigger>
      <PopoverContent className="max-w-md text-sm">
        {children}
      </PopoverContent>
    </Popover>
  );
}
