import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Position } from "@xyflow/react";
import { CanvasInspector } from "../components/canvas/canvas-inspector";
import { ArynEdge } from "../components/canvas/edges/aryn-edge";
import { studioFixture, versionA } from "./studio-fixtures";
import type { BaseNodeData } from "../components/canvas/types";
import type { Evaluation } from "../lib/types";
import { buildBenchNodesAndEdges } from "../components/canvas/canvas-builders";

const agent: BaseNodeData = {
  id: "node-agent",
  label: "Agent A",
  nodeType: "agent",
  status: "idle",
};
describe("inspector dan motion", () => {
  it("current/published hanya baca; rancangan menyimpan konfigurasi versi baru", async () => {
    const create = vi.fn(async () => {});
    const source = Object.freeze({ ...versionA });
    render(
      <CanvasInspector
        mode="factory"
        selectedNode={agent}
        onClose={() => {}}
        version={source}
        workspace={studioFixture().workspace}
        versions={[source]}
        onCreateVersion={create}
      />,
    );
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Rancang Versi Baru" }));
    fireEvent.change(screen.getByLabelText("Instruksi sistem"), {
      target: { value: "Instruksi rancangan baru yang aman dan lengkap." },
    });
    fireEvent.change(screen.getByLabelText("Model"), {
      target: { value: "model-b" },
    });
    fireEvent.change(screen.getByLabelText("Temperature"), {
      target: { value: "0.7" },
    });
    fireEvent.change(screen.getByLabelText("Batas output token"), {
      target: { value: "1024" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Simpan versi" }));
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        version_number: "1.0.1",
        model: "model-b",
        temperature: 0.7,
        max_tokens: 1024,
        tool_grants: [],
      }),
    );
    expect(source).toEqual(versionA);
  });
  it.each(["available", "unknown", "unavailable"] as const)(
    "provider %s mempunyai tone yang benar",
    (availability) => {
      const props = studioFixture();
      props.workspace.models[0].availability = availability;
      render(
        <CanvasInspector
          mode="factory"
          selectedNode={agent}
          onClose={() => {}}
          version={versionA}
          workspace={props.workspace}
        />,
      );
      expect(
        screen.getByText(
          availability === "available"
            ? "Model tersedia"
            : availability === "unknown"
              ? "Ketersediaan belum terverifikasi"
              : "Model tidak tersedia",
        ),
      ).toHaveClass(`availability-${availability}`);
    },
  );
  it.each([
    [4, true, "completed", "success", "Lulus"],
    [4, false, "unverified", "warning", "Tidak Terverifikasi"],
    [2, true, "failed", "error", "Gagal"],
  ] as const)(
    "Bench %s/4 verified=%s konsisten pada canvas dan inspector",
    (passed, verified, state, tone, label) => {
      const evaluation: Evaluation = {
        id: "display-only-evaluation",
        blueprint_id: versionA.blueprint_id,
        version_id: versionA.id,
        passed: passed === 4 ? 1 : 0,
        verified,
        score: passed / 4,
        passed_scenarios: passed,
        total_scenarios: 4,
        evaluated_at: versionA.created_at,
        details: [],
        provenance: {
          requested_model: versionA.model,
          payload_hash: versionA.payload_hash,
          evaluation_version: "display-only",
        },
      };
      const result = buildBenchNodesAndEdges(evaluation).nodes.find(
        (n) => n.id === "bench-evaluation",
      )!;
      expect(result.data.status).toBe(state);
      const view = render(
        <CanvasInspector
          mode="bench"
          selectedNode={result.data as BaseNodeData}
          onClose={() => {}}
          evaluation={evaluation}
        />,
      );
      expect(view.container.querySelector(".bench-score-banner")).toHaveClass(
        `text-${tone}`,
      );
      expect(
        view.container.querySelector(".bench-score-banner"),
      ).toHaveTextContent(label);
      if (!verified)
        expect(
          screen.getByText(/Hasil historis tetap disimpan/),
        ).toBeInTheDocument();
    },
  );
  it("preferensi reduced motion menghentikan SVG animateMotion saat berubah", () => {
    const original = window.matchMedia;
    const media = new EventTarget() as MediaQueryList;
    Object.defineProperty(media, "matches", { writable: true, value: false });
    window.matchMedia = () => media;
    const view = render(
      <svg>
        <ArynEdge
          sourceX={0}
          sourceY={0}
          targetX={100}
          targetY={0}
          sourcePosition={Position.Right}
          targetPosition={Position.Left}
          data={{ animated: true }}
        />
      </svg>,
    );
    expect(view.container.querySelector("animateMotion")).toBeInTheDocument();
    act(() => {
      Object.defineProperty(media, "matches", { value: true });
      media.dispatchEvent(new Event("change"));
    });
    expect(
      view.container.querySelector("animateMotion"),
    ).not.toBeInTheDocument();
    view.unmount();
    window.matchMedia = original;
  });
});
