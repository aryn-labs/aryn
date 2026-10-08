import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AgentDetail } from "../features/factory";
import { BenchPage } from "../features/bench";
import { Runs } from "../features/runs";
import {
  buildBenchNodesAndEdges,
  buildExecutionNodesAndEdges,
} from "../components/canvas/canvas-builders";
import { studioFixture, versionA } from "./studio-fixtures";
import type { Evaluation, Version } from "../lib/types";

describe("Studio UX Laboratory Regression Suite", () => {
  it("1. Factory Bench CTA menuju Bench Laboratory (/bench?versi=...), bukan membuka modal", () => {
    const fixture = studioFixture();
    const versionDraft: Version = {
      ...versionA,
      status: "draft",
    };
    fixture.data.versions = [versionDraft];
    fixture.workspace.runtime = {
      connected: true,
      ready: true,
      message: "Siap",
    };
    const blueprint = fixture.data.blueprints[0];

    render(
      <MemoryRouter initialEntries={[`/factory/${blueprint.id}`]}>
        <Routes>
          <Route
            path="/factory/:id"
            element={<AgentDetail {...fixture} blueprint={blueprint} />}
          />
          <Route
            path="/bench"
            element={<div data-testid="bench-page-target">Halaman Bench</div>}
          />
        </Routes>
      </MemoryRouter>,
    );

    // Modal bench lama tidak boleh ada
    expect(screen.queryByRole("dialog")).toBeNull();

    // CTA Bench pada detail header
    const benchBtns = screen.getAllByRole("button", {
      name: /Jalankan Bench/i,
    });
    expect(benchBtns.length).toBeGreaterThan(0);
    expect(benchBtns[0]).not.toBeDisabled();
    fireEvent.click(benchBtns[0]);

    // Navigasi ke Bench Laboratory langsung tercapai
    expect(screen.getByTestId("bench-page-target")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("2. Version selector Bench tidak pernah menampilkan evaluasi versi lain", () => {
    const fixture = studioFixture();
    const versionB: Version = {
      ...versionA,
      id: "version-b",
      blueprint_id: "agent-b",
      version_number: "2.0.0",
    };

    const evalA: Evaluation = {
      id: "eval-for-a",
      blueprint_id: "agent-a",
      version_id: "version-a",
      score: 1.0,
      total_scenarios: 4,
      passed_scenarios: 4,
      passed: 1,
      verified: true,
      evaluated_at: "2026-10-06T00:00:00Z",
      provenance: {
        evaluation_version: "1.0.0",
        requested_model: "model-a",
        payload_hash: "hash-a",
      },
      details: [
        {
          scenario_id: "scen_safety_injection_defense",
          name: "Uji Injeksi",
          category: "safety",
          passed: true,
          score: 1.0,
          actual_output: "Output A Aman",
          latency_seconds: 0.5,
          total_tokens: 100,
          actual_model: "model-a",
        },
      ],
    };

    const fixtureWithEval = {
      ...fixture,
      data: {
        ...fixture.data,
        versions: [versionA, versionB],
        evaluations: [evalA],
      },
    };

    // Render Bench untuk version-b (yang belum punya evaluasi)
    render(
      <MemoryRouter initialEntries={["/bench?versi=version-b"]}>
        <BenchPage {...fixtureWithEval} />
      </MemoryRouter>,
    );

    // Hasil/summary evaluasi milik version-a TIDAK BOLEH muncul
    expect(screen.queryByText("Output A Aman")).toBeNull();

    // State harus jujur: versi ini belum pernah dievaluasi
    expect(
      screen.getByText(/Versi ini belum pernah dievaluasi di Bench Laboratory/),
    ).toBeInTheDocument();
  });

  it("3. Scenario streaming event masuk ke node ID yang benar dan edge aktif mengikuti skenario aktual", () => {
    // Event skenario ke-3: research_accuracy
    const { nodes: nodes3, edges: edges3 } = buildBenchNodesAndEdges(
      null,
      null,
      {
        step: "scenario.started",
        scenarioId: "scen_research_accuracy_synthesis",
      },
    );

    const targetNode = nodes3.find(
      (n) =>
        (n.data.details as any)?.scenarioId ===
        "scen_research_accuracy_synthesis",
    );
    expect(targetNode?.data.status).toBe("running");

    // Skenario 1 dan 2 tidak boleh running
    const node1 = nodes3.find(
      (n) =>
        (n.data.details as any)?.scenarioId === "scen_safety_injection_defense",
    );
    const node2 = nodes3.find(
      (n) =>
        (n.data.details as any)?.scenarioId === "scen_tool_confinement_defense",
    );
    expect(node1?.data.status).toBe("idle");
    expect(node2?.data.status).toBe("idle");

    // Edge yang terhubung ke skenario 3 harus aktif beranimasi
    const activeEdge = edges3.find((e) => e.source === targetNode?.id);
    expect(activeEdge?.animated).toBe(true);

    const inactiveEdge = edges3.find((e) => e.source === node1?.id);
    expect(inactiveEdge?.animated).toBe(false);
  });

  it("4. Published agent terlihat di Execution selector walau belum assigned", () => {
    const fixture = studioFixture();
    // Buat agent-c yang published tapi belum ada di assignments
    const versionC: Version = {
      ...versionA,
      id: "version-c",
      blueprint_id: "agent-c",
      version_number: "3.0.0",
      status: "published",
    };

    const fixtureWithUnassigned = {
      ...fixture,
      data: {
        ...fixture.data,
        blueprints: [
          ...fixture.data.blueprints,
          {
            id: "agent-c",
            name: "Agent C Unassigned",
            slug: "agent-c",
            description: "",
            created_at: versionA.created_at,
          },
        ],
        versions: [...fixture.data.versions, versionC],
        // Jangan tambahkan ke assignments
      },
    };

    render(
      <MemoryRouter>
        <Runs {...fixtureWithUnassigned} />
      </MemoryRouter>,
    );

    // Opsi unassigned harus terlihat dalam selector dengan label "Belum ditugaskan"
    const selector = screen.getByLabelText("Penugasan agent");
    expect(selector).toBeInTheDocument();
    expect(
      screen.getByText(/Agent C Unassigned \(v3.0.0\) · Belum ditugaskan/),
    ).toBeInTheDocument();
  });

  it("5. Inline assignment creation bekerja langsung di Execution Inspector", async () => {
    const fixture = studioFixture();
    const versionC: Version = {
      ...versionA,
      id: "version-c",
      blueprint_id: "agent-c",
      version_number: "3.0.0",
      status: "published",
    };

    const actMock = vi.fn().mockResolvedValue({ id: "assignment-new-c" });

    const fixtureWithUnassigned = {
      ...fixture,
      act: actMock,
      data: {
        ...fixture.data,
        blueprints: [
          ...fixture.data.blueprints,
          {
            id: "agent-c",
            name: "Agent C",
            slug: "agent-c",
            description: "",
            created_at: versionA.created_at,
          },
        ],
        versions: [...fixture.data.versions, versionC],
        permissions: {
          ...fixture.data.permissions,
          "agent:assign": true,
        },
      },
    };

    render(
      <MemoryRouter>
        <Runs {...fixtureWithUnassigned} />
      </MemoryRouter>,
    );

    // Pilih agent C yang belum ditugaskan
    fireEvent.change(screen.getByLabelText("Penugasan agent"), {
      target: { value: "version-c" },
    });

    // Form inline penugasan harus muncul di Inspector
    expect(
      screen.getByText(
        /Agent ini telah dipublikasikan namun belum memiliki penugasan operasional/,
      ),
    ).toBeInTheDocument();

    const roleInput = screen.getByLabelText("Peran operasional penugasan");
    fireEvent.change(roleInput, { target: { value: "Analis Keuangan" } });

    const createAssignBtn = screen.getByRole("button", {
      name: "Buat Penugasan",
    });
    expect(createAssignBtn).not.toBeDisabled();
    fireEvent.click(createAssignBtn);

    expect(actMock).toHaveBeenCalledWith(
      "/assignments",
      expect.objectContaining({
        blueprint_id: "agent-c",
        version_id: "version-c",
        role_name: "Analis Keuangan",
      }),
      expect.any(String),
    );
  });

  it("6. Assigned agent langsung siap dijalankan dengan prompt + consent + tombol Run", () => {
    const fixture = studioFixture();
    render(
      <MemoryRouter>
        <Runs
          {...fixture}
          workspace={{
            ...fixture.workspace,
            runtime: { connected: true, ready: true, message: "Siap" },
          }}
        />
      </MemoryRouter>,
    );

    // Form langsung menampilkan input riset dan persetujuan
    const promptInput = screen.getByLabelText("Instruksi riset");
    expect(promptInput).toBeInTheDocument();

    const consentCheckbox = screen.getByRole("checkbox");
    expect(consentCheckbox).toBeInTheDocument();

    const runBtn = screen.getByRole("button", { name: "Jalankan agent" });
    expect(runBtn).toBeInTheDocument();
    expect(runBtn).toBeDisabled(); // Disabled karena belum ada prompt & consent

    // Isi prompt dan centang consent
    fireEvent.change(promptInput, {
      target: { value: "Analisis portofolio investasi Q3." },
    });
    fireEvent.click(consentCheckbox);

    // Tombol Run siap dijalankan
    expect(runBtn).not.toBeDisabled();
  });

  it("7. Duplicate legacy execution form dan result card tidak ada lagi di DOM", () => {
    const fixture = studioFixture();
    const { container } = render(
      <MemoryRouter initialEntries={["/runs?hasil=run-a"]}>
        <Runs {...fixture} />
      </MemoryRouter>,
    );

    // Panel legacy form duplikat di bawah canvas harus sudah dihapus
    expect(container.querySelector(".run-panel-execution")).toBeNull();
    expect(container.querySelector(".run-result-container")).toBeNull();

    // Inspector canvas adalah satu-satunya surface eksekusi
    expect(
      screen.getByRole("region", { name: "Inspector Node" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("application", { name: /Canvas ARYN/i }),
    ).toBeInTheDocument();
  });

  it("8. No fake progress: Node dan edge idle tanpa adanya actual event", () => {
    const { nodes, edges } = buildExecutionNodesAndEdges(
      null,
      null,
      "Agent Standar",
      null,
    );

    // Semua node idle
    expect(nodes.every((n) => n.data.status === "idle")).toBe(true);

    // Semua edge tidak beranimasi
    expect(edges.every((e) => !e.animated)).toBe(true);
  });
});
