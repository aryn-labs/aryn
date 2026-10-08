import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { App } from "../studio";
import { api, ApiError } from "../lib/api";
import { Overview } from "../features/overview";
import { studioFixture, summaryFixture } from "./studio-fixtures";
import { workspaceKey } from "../lib/workspace-types";

vi.mock("../lib/api", async (original) => ({
  ...(await original<typeof import("../lib/api")>()),
  api: vi.fn(),
}));
const read = vi.mocked(api);
beforeEach(() => {
  read.mockReset();
  localStorage.clear();
});
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}
function workspace() {
  const value = studioFixture().workspace;
  value.projects[0].name = "Workspace Alpha";
  value.projects[1].name = "Workspace Beta";
  return { ...value, organization_id: value.organization.id };
}
function summary(project: string, count: number) {
  const value = summaryFixture();
  value.project_id = project;
  value.metrics.blueprints.value = count;
  return value;
}

describe("workspace scope and honest projections", () => {
  it("home reads summary without fetching the legacy snapshot", async () => {
    read.mockImplementation(async (path) =>
      path.startsWith("/workspace") ? workspace() : summary("project-a", 17),
    );
    mount();
    await screen.findByRole("heading", { name: "Ruang kerja agent Anda." });
    expect(read.mock.calls.some(([path]) => path.endsWith("/snapshot"))).toBe(
      false,
    );
    expect(screen.getByText("17")).toBeInTheDocument();
    for (const name of [
      "WORKSPACE",
      "BUILD",
      "OPERATE",
      "INTELLIGENCE & RELIABILITY",
      "CONTROL",
    ])
      expect(screen.getByText(name)).toBeInTheDocument();
  });
  it("switch cancels old reads, drops old scope cache, and never presents their late response", async () => {
    let stale = false;
    let oldSignal: AbortSignal | undefined;
    let releaseOld!: (value: unknown) => void;
    let releaseNew!: (value: unknown) => void;
    read.mockImplementation(async (path, _, signal) => {
      if (path.startsWith("/workspace")) return workspace();
      if (path.includes("project-b"))
        return new Promise((resolve) => {
          releaseNew = resolve;
        });
      if (stale) {
        oldSignal = signal;
        return new Promise((resolve) => {
          releaseOld = resolve;
        });
      }
      return summary("project-a", 17);
    });
    const client = mount();
    await screen.findByText("17");
    stale = true;
    void client.invalidateQueries({
      queryKey: workspaceKey("org", "project-a", "summary"),
    });
    await waitFor(() => expect(oldSignal).toBeDefined());
    fireEvent.change(screen.getByLabelText("Pilih proyek"), {
      target: { value: "project-b" },
    });
    await waitFor(() => expect(oldSignal?.aborted).toBe(true));
    expect(screen.queryByText("17")).not.toBeInTheDocument();
    await act(async () => {
      releaseOld(summary("project-a", 99));
    });
    expect(screen.queryByText("99")).not.toBeInTheDocument();
    await act(async () => {
      releaseNew(summary("project-b", 42));
    });
    await screen.findByText("42");
    expect(
      client.getQueryData(workspaceKey("org", "project-a", "summary")),
    ).toBeUndefined();
  });
  it("403 revalidation hides previously cached project data", async () => {
    let revoked = false;
    read.mockImplementation(async (path) => {
      if (path.startsWith("/workspace")) return workspace();
      if (revoked) throw new ApiError("Keanggotaan berubah", 403);
      return summary("project-a", 17);
    });
    const client = mount();
    await screen.findByText("17");
    revoked = true;
    await act(async () => {
      await client.invalidateQueries({
        queryKey: workspaceKey("org", "project-a", "summary"),
      });
    });
    await screen.findByRole("heading", { name: "Akses proyek dibatasi" });
    expect(screen.queryByText("17")).not.toBeInTheDocument();
  });
  it("unknown usage is unavailable and viewer has no create/approve/run action", () => {
    const value = summaryFixture();
    value.permissions = {};
    render(
      <MemoryRouter>
        <Overview
          summary={value}
          workspace={workspace()}
          project="project-b"
          openBlueprint={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(
      screen.queryByRole("button", { name: "Buat agent" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Tinjau persetujuan" }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("Tidak tersedia").length).toBeGreaterThan(0);
  });
});
