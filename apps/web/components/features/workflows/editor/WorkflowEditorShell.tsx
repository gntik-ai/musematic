"use client";

import { useRef, useState } from "react";
import type { PanelImperativeHandle } from "react-resizable-panels";
import { Eye, EyeOff } from "lucide-react";
import { MonacoYamlEditor } from "@/components/features/workflows/editor/MonacoYamlEditor";
import { WorkflowGraphPreview } from "@/components/features/workflows/editor/WorkflowGraphPreview";
import { EditorToolbar } from "@/components/features/workflows/editor/EditorToolbar";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { Button } from "@/components/ui/button";
import { useMediaQuery } from "@/lib/hooks/use-media-query";
import type { WorkflowIR } from "@/types/workflows";

interface WorkflowEditorShellProps {
  workflowId?: string | null;
  initialYamlContent?: string;
  initialVersionId?: string | null;
  versionNumber?: number | null;
  compiledIr?: WorkflowIR | null;
}

export function WorkflowEditorShell({
  workflowId = null,
  initialYamlContent = "",
  initialVersionId = null,
  versionNumber = null,
  compiledIr = null,
}: WorkflowEditorShellProps) {
  const previewPanelRef = useRef<PanelImperativeHandle | null>(null);
  const [isPreviewCollapsed, setIsPreviewCollapsed] = useState(false);
  const isMobile = useMediaQuery("(max-width: 1023px)");

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button
          onClick={() => {
            if (!previewPanelRef.current) {
              return;
            }

            if (previewPanelRef.current.isCollapsed()) {
              previewPanelRef.current.expand();
              setIsPreviewCollapsed(false);
              return;
            }

            previewPanelRef.current.collapse();
            setIsPreviewCollapsed(true);
          }}
          size="sm"
          variant="outline"
        >
          {isPreviewCollapsed ? (
            <>
              <Eye className="h-4 w-4" />
              Show Preview
            </>
          ) : (
            <>
              <EyeOff className="h-4 w-4" />
              Hide Preview
            </>
          )}
        </Button>
      </div>

      <EditorToolbar workflowId={workflowId} versionNumber={versionNumber} />

      <div className="overflow-hidden rounded-3xl border border-border/60 bg-card/70 shadow-sm">
        <ResizablePanelGroup
          className="min-h-[720px]"
          id="workflow-editor-shell"
          orientation={isMobile ? "vertical" : "horizontal"}
        >
          <ResizablePanel defaultSize={isMobile ? 55 : 60} minSize={isMobile ? 30 : 35}>
            <div className="h-full p-3">
              <MonacoYamlEditor
                initialValue={initialYamlContent}
                initialVersionId={initialVersionId}
              />
            </div>
          </ResizablePanel>

          <ResizableHandle />

          <ResizablePanel
            collapsedSize={0}
            collapsible
            defaultSize={isMobile ? 45 : 40}
            minSize={isMobile ? 25 : 25}
            onResize={(size) => {
              setIsPreviewCollapsed(size.asPercentage === 0);
            }}
            panelRef={previewPanelRef}
          >
            <div className="h-full p-3">
              <WorkflowGraphPreview
                baselineYamlContent={initialYamlContent}
                compiledIr={compiledIr}
              />
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  );
}
