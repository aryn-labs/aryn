import { describe, it, expect } from "vitest";
import { readRunCompletion } from "../lib/api";
import { buildExecutionNodesAndEdges } from "../components/canvas/canvas-builders";
import { date } from "../lib/utils";
import type { RunResponse } from "../lib/types";

const result: RunResponse = {
  id: "run-captured",
  run_id: "run-captured",
  status: "completed",
  model: "test/model",
  requested_model: "test/model",
  actual_model: "test/model",
  provider: "isolated",
  runtime_backend: "Hermes",
  gateway: "9Router",
  assignment_id: "assignment",
  agent_version_id: "version",
  agent_payload_hash: "a".repeat(64),
  assignment_transition_id: "transition",
  runtime_run_id: "runtime",
  execution_provenance: { version_id: "version" },
  effective_limits: { max_total_tokens: 4096 },
  output: "Evidence",
  output_reference: "core:run:run-captured:output",
  error_code: null,
  execution_claim_verified: true,
  assignment_provenance_verified: true,
  usage: {
    input_tokens: 20,
    output_tokens: 30,
    total_tokens: 50,
    availability: "measured",
    cost_usd: null,
  },
};
describe("captured Core run result contract", () => {
  it("accepts the same persisted envelope for new, SSE and cached completion", () => {
    expect(readRunCompletion(JSON.parse(JSON.stringify(result)))).toEqual(
      result,
    );
  });
  it.each([
    "queued",
    "started",
    "running",
    "stopping",
    "failed",
    "cancelled",
    "outcome_unknown",
  ] as const)("preserves %s without inventing actual usage", (status) => {
    const pending = {
      ...result,
      status,
      actual_model: null,
      output_reference: null,
      usage: {
        ...result.usage,
        availability: "unavailable" as const,
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
      },
    };
    expect(readRunCompletion(pending).status).toBe(status);
  });
  it.each([
    { id: "other" },
    { actual_model: "substituted" },
    { execution_claim_verified: false },
    { assignment_provenance_verified: false },
    { assignment_transition_id: null },
    { usage: { ...result.usage, total_tokens: 99 } },
  ])("rejects incomplete or conflicting authority fields", (change) => {
    expect(() => readRunCompletion({ ...result, ...change })).toThrow(
      "Kontrak hasil Core tidak valid",
    );
  });
  it("uses UTC seconds consistently with historical ISO values", () => {
    expect(date(1700000000)).toBe(date(new Date(1700000000000).toISOString()));
  });
  it("shows an unknown execution as unverified, never completed", () => {
    const run = {
      id: "run",
      status: "outcome_unknown",
      prompt: "Research",
      output: "",
      model: "test/model",
      provider: "isolated",
      total_tokens: 0,
      input_tokens: 0,
      output_tokens: 0,
      created_at: 1700000000,
      session_id: "assignment",
    };
    const { nodes } = buildExecutionNodesAndEdges(run);
    expect(nodes.find((n) => n.id === "exec-runtime")?.data.status).toBe(
      "unverified",
    );
    expect(nodes.some((n) => n.data.status === "unverified")).toBe(true);
  });
});
