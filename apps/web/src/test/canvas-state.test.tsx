import { describe, expect, it } from "vitest";
import {
  buildBenchNodesAndEdges,
  buildExecutionNodesAndEdges,
  buildFactoryNodesAndEdges,
} from "../components/canvas/canvas-builders";
import type { Evaluation } from "../lib/types";
import { studioFixture, versionA } from "./studio-fixtures";

const evaluation: Evaluation = {
  id: "display-eval",
  blueprint_id: "agent-a",
  version_id: versionA.id,
  passed: 1,
  verified: false,
  score: 1,
  passed_scenarios: 4,
  total_scenarios: 4,
  evaluated_at: versionA.created_at,
  details: [],
  provenance: {
    requested_model: "model-a",
    evaluation_version: "test",
    payload_hash: "test",
  },
};
describe("state canvas berasal dari evidence", () => {
  it("metadata rencana Bench sesuai empat skenario suite nyata", () => {
    const graph = buildBenchNodesAndEdges();
    const scenarioIds = graph.nodes
      .filter((n) => n.type === "scenario")
      .map((n) => (n.data.details as { scenarioId: string }).scenarioId);
    expect(scenarioIds).toEqual([
      "scen_safety_injection_defense",
      "scen_tool_confinement_defense",
      "scen_research_accuracy_synthesis",
      "scen_grounded_abstention",
    ]);
  });
  it("skor 2/4 gagal meskipun flag passed tidak konsisten", () => {
    const graph = buildBenchNodesAndEdges({
      ...evaluation,
      verified: true,
      score: 0.5,
      passed_scenarios: 2,
    });
    expect(
      graph.nodes.find((n) => n.id === "bench-evaluation")?.data.status,
    ).toBe("failed");
  });
  it("approval historis tidak kembali menjadi perlu persetujuan saat bukti tidak berlaku", () => {
    const graph = buildFactoryNodesAndEdges(
      studioFixture().data.blueprints[0],
      {
        ...versionA,
        status: "approved",
        governance_valid: false,
      },
    );
    const approval = graph.nodes.find((n) => n.id === "node-approval")!;
    expect(approval.data.badge).toBe("Sudah disetujui · bukti tidak berlaku");
    expect(approval.data.status).toBe("blocked");
    expect(approval.data.badgeVariant).toBe("amber");
  });
  it("request pending tidak mengarang trace per-node", () => {
    const graph = buildExecutionNodesAndEdges(
      studioFixture().data.runs[0],
      versionA,
    );
    expect(graph.nodes.filter((n) => n.data.status === "running")).toHaveLength(
      0,
    );
    expect(graph.edges.some((e) => e.data?.animated)).toBe(false);
  });
  it.each(["unknown", "unavailable"] as const)(
    "model %s tidak memakai badge success",
    (availability) => {
      const props = studioFixture();
      props.workspace.models[0].availability = availability;
      const graph = buildFactoryNodesAndEdges(
        props.data.blueprints[0],
        versionA,
        props.workspace,
      );
      expect(
        graph.nodes.find((n) => n.id === "node-model")?.data.badgeVariant,
      ).toBe(availability === "unknown" ? "amber" : "rose");
    },
  );
});
