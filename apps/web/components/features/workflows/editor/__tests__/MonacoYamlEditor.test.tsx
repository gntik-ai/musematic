import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MonacoYamlEditor } from "@/components/features/workflows/editor/MonacoYamlEditor";
import { renderWithProviders } from "@/test-utils/render";
import { useWorkflowEditorStore } from "@/lib/stores/workflow-editor-store";

const configureMonacoYamlMock = vi.fn();

vi.mock("next/dynamic", () => ({
  default: (loader: () => Promise<unknown>) => {
    const DynamicComponent = (props: Record<string, unknown>) => {
      const [Component, setComponent] = React.useState<React.ComponentType<Record<string, unknown>> | null>(null);

      React.useEffect(() => {
        let active = true;

        void Promise.resolve(loader()).then((module) => {
          const resolved = (module as { default?: React.ComponentType<Record<string, unknown>> }).default ??
            (module as React.ComponentType<Record<string, unknown>>);

          if (active) {
            setComponent(() => resolved);
          }
        });

        return () => {
          active = false;
        };
      }, [loader]);

      return Component ? <Component {...props} /> : null;
    };

    return DynamicComponent;
  },
}));

vi.mock("monaco-yaml", () => ({
  configureMonacoYaml: (...args: unknown[]) => configureMonacoYamlMock(...args),
}));

vi.mock("@monaco-editor/react", () => {
  const mockMonaco = {
    MarkerSeverity: {
      Error: 8,
    },
    languages: {
      register: vi.fn(),
    },
  };

  const Editor = ({
    beforeMount,
    onChange,
    onValidate,
    value,
  }: {
    beforeMount?: ((monaco: typeof mockMonaco) => void) | undefined;
    onChange?: ((value: string | undefined) => void) | undefined;
    onValidate?: ((markers: Array<Record<string, unknown>>) => void) | undefined;
    value?: string | undefined;
  }) => {
    React.useEffect(() => {
      beforeMount?.(mockMonaco);
    }, [beforeMount]);

    React.useEffect(() => {
      if ((value ?? "").includes("missing_type")) {
        onValidate?.([
          {
            startLineNumber: 4,
            startColumn: 5,
            message: "Missing step type",
            severity: 8,
          },
        ]);
        return;
      }

      onValidate?.([]);
    }, [onValidate, value]);

    return (
      <textarea
        aria-label="Workflow YAML editor"
        data-testid="monaco-editor"
        onChange={(event) => {
          onChange?.(event.currentTarget.value);
        }}
        value={value ?? ""}
      />
    );
  };

  return {
    Editor,
  };
});

describe("MonacoYamlEditor", () => {
  beforeEach(() => {
    configureMonacoYamlMock.mockReset();
    configureMonacoYamlMock.mockReturnValue({
      update: vi.fn(),
      getOptions: vi.fn(() => ({})),
      dispose: vi.fn(),
    });
    useWorkflowEditorStore.getState().reset();
  });

  it("debounces YAML updates and surfaces diagnostics in the header", async () => {
    renderWithProviders(<MonacoYamlEditor initialValue="" />);

    const editor = await screen.findByTestId("monaco-editor");
    fireEvent.change(editor, {
      target: {
        value: [
          "name: Demo Workflow",
          "steps:",
          "  first_step:",
          "    missing_type: true",
        ].join("\n"),
      },
    });

    expect(useWorkflowEditorStore.getState().yamlContent).toBe("");

    await act(async () => {
      await new Promise((resolve) => {
        setTimeout(resolve, 550);
      });
    });

    await waitFor(() => {
      expect(useWorkflowEditorStore.getState().yamlContent).toContain("Demo Workflow");
    });

    await waitFor(() => {
      expect(useWorkflowEditorStore.getState().validationErrors).toHaveLength(1);
    });

    expect(screen.getByText(/4 lines • 1 diagnostic/i)).toBeInTheDocument();
    expect(configureMonacoYamlMock).toHaveBeenCalled();
  });
});
