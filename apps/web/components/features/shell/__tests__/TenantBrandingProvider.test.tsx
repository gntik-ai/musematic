import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  TenantBrandingProvider,
  useTenantContext,
} from "@/components/features/shell/TenantBrandingProvider";

function Probe() {
  const tenant = useTenantContext();
  return (
    <div>
      <span>{tenant.displayName}</span>
      <span>{tenant.branding.accent_color_hex}</span>
    </div>
  );
}

describe("TenantBrandingProvider", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("injects tenant context from the resolver endpoint", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "11111111-1111-1111-1111-111111111111",
        slug: "acme",
        kind: "enterprise",
        status: "active",
        display_name: "Acme Corp",
        branding: { accent_color_hex: "#123456" },
      }),
    } as Response);

    render(
      <TenantBrandingProvider>
        <Probe />
      </TenantBrandingProvider>,
    );

    await waitFor(() => expect(screen.getByText("Acme Corp")).toBeInTheDocument());
    expect(screen.getByText("#123456")).toBeInTheDocument();
  });

  it("falls back to default branding when fields are missing", () => {
    render(
      <TenantBrandingProvider
        initialTenant={{
          id: "00000000-0000-0000-0000-000000000001",
          slug: "default",
          displayName: "Musematic",
          kind: "default",
          status: "active",
          branding: {},
        }}
      >
        <Probe />
      </TenantBrandingProvider>,
    );

    expect(screen.getByText("Musematic")).toBeInTheDocument();
    expect(screen.getByText("#0078d4")).toBeInTheDocument();
  });
});
