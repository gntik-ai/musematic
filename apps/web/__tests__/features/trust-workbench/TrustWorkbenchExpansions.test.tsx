import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => <svg>{children}</svg>,
  Line: () => <path data-testid="line" />,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
}));
import { CertificationExpiryDashboard } from "@/components/features/trust/certification-expiry-dashboard";
import { CertifiersTab } from "@/components/features/trust/certifiers-tab";
import { SurveillancePanel } from "@/components/features/trust/surveillance-panel";
import { renderWithProviders } from "@/test-utils/render";
import { seedTrustWorkbenchStores } from "./test-helpers";

const replaceSpy = vi.fn();
let searchParams = new URLSearchParams("tab=expiries");
const createCertifierSpy = vi.fn().mockResolvedValue(undefined);
const deleteCertifierSpy = vi.fn().mockResolvedValue(undefined);

vi.mock("next/navigation", () => ({
  usePathname: () => "/trust-workbench",
  useRouter: () => ({ replace: replaceSpy }),
  useSearchParams: () => searchParams,
}));

vi.mock("@/lib/hooks/use-third-party-certifiers", () => ({
  useThirdPartyCertifiers: () => ({
    certifiers: [
      {
        id: "certifier-1",
        displayName: "External Certifier",
        endpoint: "https://certifier.musematic.dev",
        scope: ["global"],
        publicKeyFingerprint: "fingerprint-1",
      },
    ],
  }),
  useCertifierMutations: () => ({
    createCertifier: { mutateAsync: createCertifierSpy, isPending: false },
    deleteCertifier: { mutateAsync: deleteCertifierSpy, isPending: false },
  }),
}));

vi.mock("@/lib/hooks/use-certification-expiries", () => ({
  useCertificationExpiries: () => ({
    items: [
      {
        id: "expiry-1",
        agentFqn: "risk:fraud-monitor",
        certifierName: "Trust Board",
        issuedAt: "2026-04-10T00:00:00.000Z",
        expiresAt: "2026-04-22T00:00:00.000Z",
        status: "amber",
      },
    ],
    isLoading: false,
  }),
}));

vi.mock("@/lib/hooks/use-agents", () => ({
  useAgents: () => ({
    agents: [
      { fqn: "risk:fraud-monitor", name: "Fraud Monitor" },
      { fqn: "risk:kyc-review", name: "KYC Review" },
    ],
  }),
}));

vi.mock("@/lib/hooks/use-surveillance-signals", () => ({
  useSurveillanceSignals: (agentId: string) => ({
    signals:
      agentId === "risk:kyc-review"
        ? [
            {
              id: "signal-2",
              agentId,
              signalType: "policy_drift",
              score: 0.31,
              timestamp: "2026-04-20T10:00:00.000Z",
              summary: "KYC review drift detected",
            },
          ]
        : [
            {
              id: "signal-1",
              agentId,
              signalType: "execution_quality",
              score: 0.91,
              timestamp: "2026-04-20T09:00:00.000Z",
              summary: "Fraud monitor is stable",
            },
          ],
  }),
}));

describe("trust workbench expansions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchParams = new URLSearchParams("tab=expiries");
    seedTrustWorkbenchStores();
  });

  it("validates HTTPS and PEM before creating a certifier", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CertifiersTab />);

    await user.type(screen.getByLabelText("Display name"), "Bad Certifier");
    await user.clear(screen.getByLabelText("Endpoint"));
    await user.type(screen.getByLabelText("Endpoint"), "http://insecure.example.com");
    await user.clear(screen.getByLabelText("PEM public key"));
    await user.type(screen.getByLabelText("PEM public key"), "not a pem");
    await user.click(screen.getByRole("button", { name: "Add certifier" }));

    expect(screen.getByText("Endpoint must use HTTPS.")).toBeInTheDocument();
    expect(screen.getByText("PEM header/footer is invalid.")).toBeInTheDocument();
    expect(createCertifierSpy).not.toHaveBeenCalled();
  });

  it("creates a valid certifier entry", async () => {
    const user = userEvent.setup();
    renderWithProviders(<CertifiersTab />);

    await user.type(screen.getByLabelText("Display name"), "Regulated Certifier");
    await user.clear(screen.getByLabelText("Endpoint"));
    await user.type(screen.getByLabelText("Endpoint"), "https://regulated.example.com");
    await user.clear(screen.getByLabelText("PEM public key"));
    await user.type(
      screen.getByLabelText("PEM public key"),
      "-----BEGIN PUBLIC KEY-----\nabc123\n-----END PUBLIC KEY-----",
    );
    await user.click(screen.getByRole("button", { name: "Add certifier" }));

    await waitFor(() =>
      expect(createCertifierSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          displayName: "Regulated Certifier",
          endpoint: "https://regulated.example.com",
        }),
      ),
    );
  });

  it("persists the expiry sort to the URL when the header is toggled", () => {
    renderWithProviders(<CertificationExpiryDashboard defaultSort="expires_at_asc" />);

    fireEvent.click(screen.getByRole("button", { name: "Agent FQN" }));

    expect(replaceSpy).toHaveBeenCalledWith("/trust-workbench?tab=expiries&sort=agent_fqn");
  });

  it("switches surveillance signals when a different agent is selected", () => {
    renderWithProviders(<SurveillancePanel agentId="risk:fraud-monitor" />);

    expect(screen.getByText("Fraud monitor is stable")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Agent"), {
      target: { value: "risk:kyc-review" },
    });

    expect(screen.getByText("KYC review drift detected")).toBeInTheDocument();
  });
});
