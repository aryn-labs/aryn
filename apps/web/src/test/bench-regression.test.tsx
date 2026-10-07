import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RegressionPanel } from "../features/bench";
import { needsApproval } from "../lib/studio-state";
import { versionA } from "./studio-fixtures";
import type { RegressionComparison } from "../lib/types";

const identity = {
  evaluation_id: "prior-evaluation",
  version_id: "prior-version",
  version_number: "1.0.0",
  payload_hash: "hash",
  evidence_hash: "evidence",
  evidence_format: 2 as const,
};
const comparison: RegressionComparison = {
  comparison_id: "comparison",
  blueprint_id: "blueprint",
  baseline_id: "baseline",
  baseline: identity,
  candidate: {
    ...identity,
    evaluation_id: "candidate-evaluation",
    version_id: "candidate",
    version_number: "2.0.0",
  },
  suite_id: "structured-analysis",
  evaluation_version: "2.1.0",
  suite_hash: "configuration",
  compared_at: "2026-10-08T00:00:00Z",
  state: "comparable",
  reason: "critical_regression",
  promotion_blocked: true,
  baseline_score: 1,
  candidate_score: 0.5,
  score_delta: -0.5,
  limitations: [],
  metrics: {
    latency_seconds: {
      state: "comparable",
      baseline: 1,
      candidate: 2,
      delta: 1,
    },
    cost_usd: { state: "unavailable" },
  },
  scenarios: [
    {
      scenario_id: "extraction",
      scenario_version: "1.0.0",
      baseline_state: "passed",
      candidate_state: "failed",
      regression: true,
      critical: true,
      graders: [
        {
          grader_id: "schema",
          grader_type: "schema_validity",
          grader_version: "1.0.0",
          baseline_state: "passed",
          candidate_state: "failed",
          regression: true,
          critical: true,
          candidate_reason: "required_field_missing",
        },
      ],
    },
  ],
  regressions: [],
  critical_regressions: [
    {
      kind: "scenario",
      reason: "scenario_state_regressed",
      critical: true,
      details: {},
    },
  ],
};

describe("authoritative Bench regression presentation", () => {
  it("shows baseline/candidate identities and critical evidence despite a passing aggregate", () => {
    render(<RegressionPanel comparison={comparison} />);
    expect(
      screen.getByText("Accepted Baseline vs Candidate"),
    ).toBeInTheDocument();
    expect(screen.getByText("v1.0.0")).toBeInTheDocument();
    expect(screen.getByText("v2.0.0")).toBeInTheDocument();
    expect(screen.getByText(/Promotion diblokir/)).toBeInTheDocument();
    expect(screen.getByText(/1 regression kritis/)).toBeInTheDocument();
    expect(screen.getByText("extraction")).toBeInTheDocument();
    expect(screen.getByText(/schema_validity/)).toBeInTheDocument();
    expect(screen.getByText("unavailable")).toBeInTheDocument();
    expect(
      needsApproval({
        ...versionA,
        bench_eligible: true,
        integrity_valid: true,
        status: "draft",
        regression: comparison,
      }),
    ).toBe(false);
  });
  it("shows explicit bootstrap and a non-regressing review decision", () => {
    render(
      <RegressionPanel
        comparison={{
          ...comparison,
          baseline: null,
          baseline_id: null,
          state: "bootstrap",
          scenarios: [],
          critical_regressions: [],
          promotion_blocked: false,
          score_delta: null,
        }}
      />,
    );
    expect(
      screen.getByText("Bootstrap publication pertama"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Eligible untuk tinjauan promotion/),
    ).toBeInTheDocument();
  });
  it("surfaces incompatibility and legacy limitations", () => {
    render(
      <RegressionPanel
        comparison={{
          ...comparison,
          state: "incompatible",
          limitations: ["legacy_scenario_evidence_only"],
          regressions: [
            {
              kind: "comparability",
              reason: "suite_or_evidence_format_changed",
              critical: true,
              details: {},
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByText("suite_or_evidence_format_changed"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("legacy_scenario_evidence_only"),
    ).toBeInTheDocument();
  });
});
