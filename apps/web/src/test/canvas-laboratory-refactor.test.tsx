import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AgentDetail } from "../features/factory";
import { BenchPage } from "../features/bench";
import {
  buildFactoryNodesAndEdges,
  buildBenchNodesAndEdges,
  buildExecutionNodesAndEdges,
} from "../components/canvas/canvas-builders";
import { studioFixture } from "./studio-fixtures";
import type { Blueprint } from "../lib/types";

describe("Regression Refactor: Canvas-First Laboratory & Truthful Events", () => {
  it("Factory canvas tampil sebelum versi pertama dibuat dengan state tidak terkonfigurasi yang jujur", () => {
    const fixture = studioFixture();
    const unconfiguredBlueprint: Blueprint = {
      id: "bp-new",
      name: "Blueprint Baru",
      slug: "blueprint-baru",
      description: "Belum memiliki versi",
      created_at: "2026-10-06T00:00:00Z",
    };

    const { nodes, edges } = buildFactoryNodesAndEdges(
      unconfiguredBlueprint,
      undefined,
      fixture.workspace,
      fixture.project,
    );

    const agentNode = nodes.find((n) => n.id === "node-agent");
    const modelNode = nodes.find((n) => n.id === "node-model");
    const outputNode = nodes.find((n) => n.id === "node-output");

    expect(agentNode?.data.label).toBe("Blueprint Baru");
    expect(agentNode?.data.badge).toBe("Belum dikonfigurasi");
    expect(modelNode?.data.label).toBe("Model belum dipilih");
    expect(outputNode?.data.badge).toBe("Output kosong");

    // All edges in unconfigured state must NOT be animated
    expect(edges.every((e) => !e.animated)).toBe(true);

    // Verify rendered in DOM
    render(
      <MemoryRouter>
        <AgentDetail {...fixture} blueprint={unconfiguredBlueprint} />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("application", { name: /Canvas ARYN/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Blueprint ini belum dikonfigurasi/),
    ).toBeInTheDocument();
  });

  it("Bench canvas tampil sebelum evaluasi dengan 4 skenario suite standar dalam state belum dijalankan", () => {
    const { nodes, edges } = buildBenchNodesAndEdges(null);

    const scenarioNodes = nodes.filter((n) => n.data.nodeType === "scenario");
    expect(scenarioNodes).toHaveLength(4);
    expect(scenarioNodes.every((n) => n.data.status === "idle")).toBe(true);
    expect(edges.every((e) => !e.animated)).toBe(true);

    const fixture = studioFixture();
    const emptyEvaluationsFixture = {
      ...fixture,
      data: {
        ...fixture.data,
        evaluations: [],
      },
    };

    render(
      <MemoryRouter>
        <BenchPage {...emptyEvaluationsFixture} />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("application", { name: /Canvas ARYN/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Jalankan Bench/i }),
    ).toBeInTheDocument();
  });

  it("Tombol Run Bench bekerja dari Bench canvas workspace", async () => {
    const fixture = studioFixture();
    const actStreamMock = vi.fn().mockResolvedValue({ id: "eval-new" });

    render(
      <MemoryRouter>
        <BenchPage
          {...fixture}
          act={actStreamMock}
          actStream={actStreamMock}
          workspace={{
            ...fixture.workspace,
            runtime: { connected: true, ready: true, message: "Siap" },
          }}
        />
      </MemoryRouter>,
    );

    const runBtn = screen.getByRole("button", { name: /Jalankan Bench/i });
    expect(runBtn).not.toBeDisabled();
    fireEvent.click(runBtn);

    expect(actStreamMock).toHaveBeenCalledWith(
      expect.stringContaining("/bench"),
      expect.objectContaining({ allow_remote_model: true }),
      expect.any(String),
      expect.any(Function),
    );
  });

  it("Actual Bench progress mengubah state visual node dan menganimasikan hanya edge aktif", () => {
    // 1. Idle state before running
    const { edges: idleEdges } = buildBenchNodesAndEdges(null);
    expect(idleEdges.every((e) => !e.animated)).toBe(true);

    // 2. Scenario 1 (safety_boundary) running
    const { nodes: runningNodes, edges: runningEdges } = buildBenchNodesAndEdges(
      null,
      null,
      {
        step: "scenario.started",
        scenarioIndex: 0,
        scenarioId: "safety_boundary",
      },
    );
    expect(runningNodes[0].data.status).toBe("running");
    expect(runningEdges[0].animated).toBe(true);
    expect(runningEdges[1].animated).toBe(false);
    expect(runningEdges[2].animated).toBe(false);

    // 3. Scenario completed
    const { nodes: completedNodes, edges: completedEdges } = buildBenchNodesAndEdges(
      null,
      null,
      {
        step: "scenario.completed",
        scenarioIndex: 0,
        scenarioId: "safety_boundary",
        scenarioStatuses: { 0: { passed: true, status: "completed" } },
      },
    );
    expect(completedNodes[0].data.status).toBe("completed");
    expect(completedEdges[0].animated).toBe(false);
  });

  it("Actual Run progress mengubah visual edge hanya saat event operasional aktif", () => {
    const liveRun = {
      id: "run-live",
      status: "running",
      prompt: "Test prompt",
      session_id: "assign-1",
      total_tokens: 0,
      input_tokens: 0,
      output_tokens: 0,
      created_at: "2026-10-06T00:00:00Z",
    } as any;

    // Dispatching event
    const { edges: dispatchEdges } = buildExecutionNodesAndEdges(
      liveRun,
      null,
      "Agent Live",
      { step: "runtime.dispatching" },
    );

    const dispatchEdge = dispatchEdges.find(
      (e) => e.source === "exec-agent" && e.target === "exec-model",
    );
    const persistingEdge = dispatchEdges.find(
      (e) => e.source === "exec-runtime" && e.target === "exec-output",
    );
    expect(dispatchEdge?.animated).toBe(true);
    expect(persistingEdge?.animated).toBe(false);

    // Persisting event
    const { edges: persistEdges } = buildExecutionNodesAndEdges(
      liveRun,
      null,
      "Agent Live",
      { step: "core.persisting" },
    );
    const dispatchEdge2 = persistEdges.find(
      (e) => e.source === "exec-agent" && e.target === "exec-model",
    );
    const persistingEdge2 = persistEdges.find(
      (e) => e.source === "exec-runtime" && e.target === "exec-output",
    );
    expect(dispatchEdge2?.animated).toBe(false);
    expect(persistingEdge2?.animated).toBe(true);

    // Completed run has 0 animated edges
    const completedRun = { ...liveRun, status: "completed" };
    const { edges: doneEdges } = buildExecutionNodesAndEdges(
      completedRun,
      null,
      "Agent Live",
      null,
    );
    expect(doneEdges.every((e) => !e.animated)).toBe(true);
  });

  it("Published version tetap immutable dan legacy duplicate config panel tidak ada di DOM", () => {
    const fixture = studioFixture();
    const blueprint = fixture.data.blueprints[0];

    const { container } = render(
      <MemoryRouter>
        <AgentDetail {...fixture} blueprint={blueprint} />
      </MemoryRouter>,
    );

    // Legacy duplicate detail-layout should be removed
    expect(container.querySelector(".detail-layout")).toBeNull();

    // The Canvas and Inspector are present
    expect(
      screen.getByRole("application", { name: /Canvas ARYN/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Inspector Node" }),
    ).toBeInTheDocument();

    // Published version is read-only
    expect(screen.getAllByText(/HANYA BACA/i).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Rancang Versi Baru" }),
    ).toBeInTheDocument();
  });
});
