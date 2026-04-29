"use client";

import type { LocaleFileListItem } from "@/lib/api/locales";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface LocaleVersionHistoryProps {
  versions: LocaleFileListItem[];
}

export function LocaleVersionHistory({ versions }: LocaleVersionHistoryProps) {
  if (versions.length === 0) {
    return <p className="text-sm text-muted-foreground">No published versions yet.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Locale</TableHead>
            <TableHead>Version</TableHead>
            <TableHead>Published</TableHead>
            <TableHead>Vendor ref</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {versions.map((version) => (
            <TableRow key={`${version.locale_code}-${version.version}`}>
              <TableCell className="font-medium">{version.locale_code}</TableCell>
              <TableCell>{version.version}</TableCell>
              <TableCell>
                {version.published_at
                  ? new Intl.DateTimeFormat(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(version.published_at))
                  : "Draft"}
              </TableCell>
              <TableCell>{version.vendor_source_ref ?? "None"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
