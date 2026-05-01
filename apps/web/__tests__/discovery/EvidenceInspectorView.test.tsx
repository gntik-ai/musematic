import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { EvidenceInspectorView } from "@/components/features/discovery/EvidenceInspectorView";
import { renderWithProviders } from "@/test-utils/render";
import { server } from "@/vitest.setup";

describe("EvidenceInspectorView", () => {
  it("renders aggregated and source evidence links", async () => {
    server.use(
      http.get("*/api/v1/discovery/hypotheses/hypothesis-1/critiques", () =>
        HttpResponse.json({
          aggregated: {
            critique_id: "critique-agg",
            hypothesis_id: "hypothesis-1",
            reviewer_agent_fqn: "aggregate",
            is_aggregated: true,
            scores: {
              novelty: { score: 0.83, confidence: 0.9, reasoning: "Novel link" },
            },
            composite_summary: null,
            created_at: "2026-05-01T10:00:00.000Z",
          },
          items: [
            {
              critique_id: "critique-1",
              hypothesis_id: "hypothesis-1",
              reviewer_agent_fqn: "reviewer:alpha",
              is_aggregated: false,
              scores: {
                evidence: { score: 0.7, confidence: 0.8, reasoning: "Supported" },
              },
              composite_summary: null,
              created_at: "2026-05-01T10:01:00.000Z",
            },
          ],
        }),
      ),
    );

    renderWithProviders(
      <EvidenceInspectorView hypothesisId="hypothesis-1" workspaceId="workspace-1" />,
    );

    expect(await screen.findByText("Aggregated evidence")).toBeInTheDocument();
    expect(screen.getByText("reviewer:alpha")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Source hypothesis" })[0]).toHaveAttribute(
      "href",
      "/discovery/hypothesis-1/hypotheses",
    );
    expect(screen.getByText(/novelty/)).toBeInTheDocument();
    expect(screen.getAllByText(/evidence/).length).toBeGreaterThan(0);
  });

  it("renders an explicit unavailable state when no evidence exists", async () => {
    server.use(
      http.get("*/api/v1/discovery/hypotheses/hypothesis-empty/critiques", () =>
        HttpResponse.json({ aggregated: null, items: [] }),
      ),
    );

    renderWithProviders(
      <EvidenceInspectorView hypothesisId="hypothesis-empty" workspaceId="workspace-1" />,
    );

    expect(
      await screen.findByText(
        "Source unavailable or no critique evidence has been recorded for this hypothesis.",
      ),
    ).toBeInTheDocument();
  });
});
