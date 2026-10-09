import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Automations, Capabilities } from "../features/automations";
import { api, ApiError } from "../lib/api";
import { studioFixture } from "./studio-fixtures";
import type { CapabilityRegistry } from "../lib/automation-types";

vi.mock("../lib/api", async () => ({
  ...(await vi.importActual("../lib/api")),
  api: vi.fn(),
}));
afterEach(() => vi.resetAllMocks());
function mount(component: React.ReactNode, path: string) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>{component}</MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}
function registry(): CapabilityRegistry {
  return {
    organization_id: "org",
    project_id: "project",
    mode: "hosted",
    checked_at: "2026-10-09T00:00:00Z",
    entitlement: "unknown",
    entitlement_reason: "No verified entitlement source",
    billing_category: "external_or_local",
    provider_hard_cost_cap: false,
    scheduler_authority: "core_single_owner",
    local_offline_execution: false,
    capabilities: [
      {
        namespace: "host.file",
        version: "1",
        adapter: "unavailable",
        modes: ["local", "hosted"],
        risk: "privileged",
        available: false,
        effective_permission: false,
        grants: [],
        requirements: ["verified privileged mediation"],
        missing_prerequisites: ["mediation unavailable"],
        disabled_reason: "Default deny; no host sandbox",
      },
    ],
  };
}
describe("Core control surfaces use current scoped authority", () => {
  it("shows effective Hosted restrictions, unknown entitlement and no grant mutation", async () => {
    vi.mocked(api).mockResolvedValue(registry());
    mount(<Capabilities shared={studioFixture()} />, "/capabilities");
    expect(
      await screen.findByRole("heading", { name: "host.file" }),
    ).toBeVisible();
    expect(screen.getByText("hosted", { exact: true })).toBeVisible();
    expect(screen.getByText(/No verified entitlement source/)).toBeVisible();
    expect(screen.getByText(/Default deny; no host sandbox/)).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /grant|enable|unlock/i }),
    ).not.toBeInTheDocument();
    expect(
      vi.mocked(api).mock.calls.every(([, body]) => body === undefined),
    ).toBe(true);
  });
  it("403 refetch removes cached capability contents and authority", async () => {
    vi.mocked(api).mockResolvedValueOnce(registry());
    mount(<Capabilities shared={studioFixture()} />, "/capabilities");
    await screen.findByRole("heading", { name: "host.file" });
    vi.mocked(api).mockRejectedValue(
      new ApiError("Revoked current project", 403),
    );
    fireEvent.click(screen.getByRole("button", { name: "Periksa kembali" }));
    expect(
      await screen.findByRole("heading", { name: "Akses proyek dibatasi" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "host.file" }),
    ).not.toBeInTheDocument();
  });
  it("viewer has no schedule creation action and sees truthful offline semantics", async () => {
    const shared = studioFixture();
    shared.data.permissions["version:approve"] = false;
    vi.mocked(api).mockResolvedValue({
      items: [],
      next: null,
      scheduler: {
        local_device_off: "Perangkat mati: tidak berjalan",
        native_jobs: false,
      },
    });
    mount(<Automations shared={shared} />, "/automations");
    expect(
      await screen.findByText(/Perangkat mati: tidak berjalan/),
    ).toBeVisible();
    expect(
      screen.queryByRole("link", { name: "Buat jadwal" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/Belum ada jadwal yang cocok/)).toBeVisible();
    await waitFor(() =>
      expect(vi.mocked(api)).toHaveBeenCalledWith(
        expect.stringContaining("/automations?"),
        undefined,
        expect.any(AbortSignal),
      ),
    );
  });
  it("failed list reads suppress stale schedule links instead of retaining executable authority", async () => {
    vi.mocked(api).mockRejectedValue(new ApiError("Offline read", 503));
    mount(<Automations shared={studioFixture()} />, "/automations");
    expect(
      await screen.findByRole("heading", {
        name: "Data belum dapat diverifikasi",
      }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "Jalankan occurrence manual" }),
    ).not.toBeInTheDocument();
  });
});
