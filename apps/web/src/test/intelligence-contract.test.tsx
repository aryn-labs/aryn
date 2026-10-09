import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Brief, Relay, CapsuleReplays } from "../features/intelligence";
import { api, ApiError } from "../lib/api";
import { studioFixture } from "./studio-fixtures";
import type { Bundle, IncidentDetail } from "../lib/intelligence-types";

vi.mock("../lib/api", async () => ({
  ...(await vi.importActual("../lib/api")),
  api: vi.fn(),
}));
afterEach(() => vi.resetAllMocks());
const at = "2026-10-09T00:00:00Z";
function bundle(): Bundle {
  return {
    id: "bundle_one",
    title: "Component-only evidence",
    created_at: at,
    digest: "a".repeat(64),
    status: "CONFLICTING",
    hypothesis: {
      question: "Is the demo healthy?",
      predicate: "service_healthy",
      text: "",
      minimum_sources: 2,
    },
    source_ids: ["source_one", "source_two"],
    workflow: null,
    evaluation: {
      status: "CONFLICTING",
      abstention: null,
      coverage: 2,
      required_coverage: 2,
      evaluated_at: at,
      items: ["support", "conflict"].map((relationship, i) => ({
        source_id: `source_${i}`,
        relationship: relationship as "support" | "conflict",
        integrity: "VERIFIED",
        freshness: "fresh",
        excerpt: `Actual component fixture ${i}`,
        reason: "Measured demo health",
        observed_at: at,
        collected_at: at,
      })),
    },
  };
}
function incident(): IncidentDetail {
  return {
    id: "incident_one",
    title: "Component incident",
    status: "PROPOSED",
    severity: "high",
    owner_id: "owner",
    revision: 3,
    created_at: at,
    updated_at: at,
    target_id: "demo_one",
    signal_id: "signal_one",
    bundle_id: "bundle_one",
    capsule_id: null,
    fixture: {
      id: "demo_one",
      name: "Disposable",
      revision: 2,
      running: false,
      blocking_fault: false,
      disposable: true,
      updated_at: at,
    },
    signal: {
      id: "signal_one",
      source_id: "source_two",
      dedup_key: "worker",
      demo: true,
      created_at: at,
    },
    timeline: [],
    bundle: bundle(),
    approval: null,
    execution: null,
    verification: null,
    capsule: null,
    proposal: {
      id: "proposal_one",
      payload_hash: "b".repeat(64),
      target_id: "demo_one",
      target_revision: 2,
      action: "restart_demo",
      parameters: {},
      reversible_intent: "restore_prior_demo_running_state",
      preconditions: "verified_disposable_target_unhealthy_at_exact_revision",
      verification: {
        kind: "demo_health_v1",
        require_running: true,
        require_no_blocking_fault: true,
      },
      reason: "Exact target review",
      bundle_id: "bundle_one",
      bundle_digest: "a".repeat(64),
    },
  };
}
function mount(component: React.ReactNode, path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>{component}</MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}
describe("Brief/Relay current scoped authority", () => {
  it("preserves counterevidence and explicit abstention without inferred diagnosis", async () => {
    const b = bundle();
    b.evaluation.status = "INSUFFICIENT_EVIDENCE";
    b.evaluation.coverage = 1;
    b.evaluation.abstention = "Abstain: missing verified coverage.";
    b.evaluation.items[1] = {
      ...b.evaluation.items[1],
      integrity: "UNVERIFIED",
      freshness: "unavailable",
      excerpt: "",
    };
    vi.mocked(api).mockResolvedValue(b);
    mount(<Brief {...studioFixture()} />, "/brief/bundle_one");
    expect(
      await screen.findByText("Abstain: missing verified coverage."),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Counterevidence" }),
    ).toBeVisible();
    expect(
      screen.getAllByRole("button", { name: "Periksa provenance sumber" })[1],
    ).toBeDisabled();
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();
  });
  it("binds human approval to displayed hash and never enables unapproved execution", async () => {
    const d = incident(),
      fixture = studioFixture();
    fixture.data.permissions["version:approve"] = true;
    vi.mocked(api).mockImplementation(async (path, body) => {
      if (body) return {} as never;
      return (
        path.endsWith("/relay/incident_one") ? d : { items: [], next: null }
      ) as never;
    });
    mount(<Relay {...fixture} />, "/relay/incident_one");
    expect(await screen.findByTestId("proposal-hash")).toHaveTextContent(
      d.proposal!.payload_hash,
    );
    fireEvent.change(screen.getByLabelText("Alasan review manusia"), {
      target: { value: "Reviewed current exact payload" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Setujui hash proposal" }),
    );
    await waitFor(() =>
      expect(api).toHaveBeenCalledWith(
        "/projects/project-b/relay/incident_one/approve",
        {
          payload_hash: "b".repeat(64),
          reason: "Reviewed current exact payload",
        },
      ),
    );
    fireEvent.click(
      screen.getByLabelText(
        "Saya mengonfirmasi target demo dan hash proposal yang ditampilkan.",
      ),
    );
    expect(
      screen.getByRole("button", { name: "Jalankan recovery demo" }),
    ).toBeDisabled();
  });
  it("removes cached proposal controls when a current read is denied", async () => {
    let denied = false;
    vi.mocked(api).mockImplementation(async (path) => {
      if (path.endsWith("/relay/incident_one")) {
        if (denied) throw new ApiError("Membership revoked", 403);
        return incident() as never;
      }
      return { items: [], next: null } as never;
    });
    const client = mount(<Relay {...studioFixture()} />, "/relay/incident_one");
    await screen.findByTestId("proposal-hash");
    denied = true;
    await client.invalidateQueries();
    expect(
      await screen.findByRole("heading", { name: "Akses evidence dibatasi" }),
    ).toBeVisible();
    expect(screen.queryByTestId("proposal-hash")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Jalankan recovery demo" }),
    ).not.toBeInTheDocument();
  });
  it("cannot offer replay when capsule provenance is unavailable", async () => {
    vi.mocked(api).mockImplementation(async (path) => {
      if (path.includes("/relay/capsules/"))
        throw new ApiError("Capsule unverified", 409);
      return { items: [], next: null } as never;
    });
    mount(
      <CapsuleReplays {...studioFixture()} />,
      "/bench/replays?capsule=capsule_one",
    );
    expect(await screen.findByText("Capsule unverified")).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Jalankan replay memory" }),
    ).not.toBeInTheDocument();
  });
  it("unknown outcomes expose reconciliation and no action retry", async () => {
    const d = { ...incident(), status: "OUTCOME_UNKNOWN" };
    const fixture = studioFixture();
    fixture.data.permissions["version:approve"] = true;
    vi.mocked(api).mockImplementation(
      async (path) =>
        (path.endsWith("/relay/incident_one")
          ? d
          : { items: [], next: null }) as never,
    );
    mount(<Relay {...fixture} />, "/relay/incident_one");
    expect(
      await screen.findByRole("button", { name: "Rekonsiliasi health" }),
    ).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: "Jalankan recovery demo" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Tutup incident terverifikasi" }),
    ).not.toBeInTheDocument();
  });
});
