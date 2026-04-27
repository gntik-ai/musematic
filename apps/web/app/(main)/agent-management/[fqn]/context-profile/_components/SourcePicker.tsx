"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const SOURCES = ["Memory", "Knowledge graph", "Execution history", "Tool outputs", "External APIs"];

export function SourcePicker() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sources</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {SOURCES.map((source) => (
          <Badge key={source} variant="secondary">
            {source}
          </Badge>
        ))}
      </CardContent>
    </Card>
  );
}

