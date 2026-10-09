import { describe, it, expect } from "vitest";
import { draftDefinition, validateDraft } from "../lib/agent-editor-types";
import { versionDiff } from "../features/version-detail";
import { studioFixture, versionA } from "./studio-fixtures";

describe("canonical editor contracts", () => {
  it("preserves all nested source policies while creating a new candidate number", () => {
    const source = {
      ...versionA,
      metadata: { purpose: "research" },
      objective: "Grounded analysis",
      role: "researcher",
      owner: "owner",
      output_contract: {
        format: "json",
        schema_definition: { type: "object", required: ["answer"] },
        required_sections: ["Evidence"],
        description: "Response",
        strict: true,
      },
      constraints: {
        disallowed_actions: ["host access"],
        operational_rules: ["cite"],
        require_evidence_citation: true,
        max_execution_time_seconds: 60,
      },
      budget_policy: {
        max_tokens_per_run: 512,
        max_turns: 3,
        max_cost_usd: 0.1,
        timeout_seconds: 60,
      },
      model_policy: {
        primary_model: versionA.model,
        provider: "9router",
        allowed_models: [versionA.model],
        temperature: 0.3,
        max_tokens: 512,
        allow_fallback: false,
        stop_sequences: ["END"],
      },
      evaluation_reference: {
        suite_id: "research-safety-1.2.0",
        evaluation_version: "1.2.0",
        min_score_threshold: 1,
        required_scenarios: ["scen_grounded_abstention"],
        evaluation_id: null,
      },
    };
    const value = draftDefinition(studioFixture().data.blueprints[0], source);
    expect(value.version_number).toBe("1.0.1");
    for (const field of [
      "output_contract",
      "constraints",
      "budget_policy",
      "model_policy",
      "evaluation_reference",
      "metadata",
    ] as const)
      expect(value[field]).toEqual(source[field]);
    expect(value.tool_grants).toEqual([]);
    expect(value.tool_policy.network_access).toBe(false);
    expect(validateDraft(value)).toEqual([]);
    expect(source.version_number).toBe("1.0.0");
  });
  it("reports prompt/model/token validation and compares nested changes", () => {
    const value = draftDefinition(studioFixture().data.blueprints[0], versionA);
    expect(
      validateDraft({
        ...value,
        model: "",
        max_tokens: 10,
        system_prompt: "short",
      }),
    ).toHaveLength(3);
    const changed = {
      ...versionA,
      constraints: { operational_rules: ["cite evidence"] },
    };
    expect(versionDiff(versionA, changed)).toEqual([
      { field: "constraints", before: undefined, after: changed.constraints },
    ]);
    expect(versionDiff(versionA, versionA)).toEqual([]);
    expect(
      versionDiff(
        { ...versionA, metadata: { a: 1, b: 2 } },
        { ...versionA, metadata: { b: 2, a: 1 } },
      ),
    ).toEqual([]);
  });
});
