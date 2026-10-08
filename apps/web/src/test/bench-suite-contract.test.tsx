import { describe, expect, it } from "vitest";
import { buildBenchNodesAndEdges } from "../components/canvas/canvas-builders";
import { evaluationStatus } from "../lib/studio-state";
import type { Evaluation, EvaluationSuite } from "../lib/types";

const suite: EvaluationSuite = {
  suite_id: "structured-analysis",
  evaluation_version: "2.1.0",
  aliases: ["analysis"],
  name: "Structured analysis",
  scenarios: [
    {
      scenario_id: "summary",
      name: "Structured summary",
      category: "summarization",
    },
    {
      scenario_id: "extract",
      name: "Structured extraction",
      category: "extraction",
    },
  ],
};
const evaluation: Evaluation = {
  id: "evaluation",
  blueprint_id: "blueprint",
  version_id: "version",
  passed: 1,
  verified: true,
  total_scenarios: 2,
  passed_scenarios: 2,
  score: 1,
  evaluated_at: "2026-10-08T00:00:00Z",
  details: suite.scenarios.map((s) => ({
    ...s,
    passed: true,
    score: 1,
    actual_output: "{}",
    latency_seconds: 1,
    actual_model: "model",
    total_tokens: 5,
  })),
  provenance: {
    evaluation_version: "2.1.0",
    requested_model: "model",
    payload_hash: "hash",
    evidence_format: 2,
    quality_gate: {
      passed: true,
      reason: "suite_policy_satisfied",
      min_score_threshold: 1,
      required_scenarios: ["summary", "extract"],
    },
  },
};

describe("generic suite presentation", () => {
  it("builds scenario nodes from authoritative suite metadata", () => {
    const graph = buildBenchNodesAndEdges(null, null, null, suite);
    const scenarios = graph.nodes.filter((n) => n.data.nodeType === "scenario");
    expect(scenarios).toHaveLength(2);
    expect(scenarios.map((n) => n.data.label)).toEqual([
      "Structured summary",
      "Structured extraction",
    ]);
  });
  it("uses persisted scenario identities and generic aggregate counts", () => {
    const graph = buildBenchNodesAndEdges(evaluation);
    expect(
      graph.nodes.filter((n) => n.data.nodeType === "scenario"),
    ).toHaveLength(2);
    expect(
      graph.nodes.find((n) => n.id === "bench-evaluation")?.data.status,
    ).toBe("completed");
    expect(evaluationStatus({ ...evaluation, verified: false })).toBe(
      "bench_unverified",
    );
  });
  it("uses suite policy thresholds without trusting an inconsistent aggregate", () => {
    const partial = {
      ...evaluation,
      passed_scenarios: 1,
      score: 0.5,
      provenance: {
        ...evaluation.provenance,
        quality_gate: {
          passed: true,
          reason: "suite_policy_satisfied",
          min_score_threshold: 0.5,
          required_scenarios: ["summary"],
        },
      },
    };
    expect(evaluationStatus(partial)).toBe("bench_passed");
    expect(evaluationStatus({ ...partial, score: 1 })).toBe("failed");
    expect(
      evaluationStatus({
        ...partial,
        provenance: {
          ...partial.provenance,
          quality_gate: { ...partial.provenance.quality_gate, passed: false },
        },
      }),
    ).toBe("failed");
  });
  it("live scenario metadata does not assume Research Safety identities", () => {
    const graph = buildBenchNodesAndEdges(null, null, {
      step: "scenario.started",
      scenarios: suite.scenarios,
      scenarioIndex: 1,
    });
    expect(
      graph.nodes.filter((n) => n.data.nodeType === "scenario"),
    ).toHaveLength(2);
    expect(
      graph.nodes.filter((n) => n.data.nodeType === "scenario")[1].data.status,
    ).toBe("running");
  });
});
