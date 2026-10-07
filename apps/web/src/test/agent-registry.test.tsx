import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VersionRegistry } from "../features/factory";
import { historicalRunContext } from "../lib/studio-state";
import { studioFixture, versionA } from "./studio-fixtures";
import type { VersionRegistryEntry } from "../lib/types";

function registryFixture() {
  const fixture = studioFixture();
  const registry: VersionRegistryEntry = {
    version_id: versionA.id,
    blueprint_id: versionA.blueprint_id,
    version_number: "1.0.0",
    status: "published",
    payload_hash: versionA.payload_hash,
    created_at: versionA.created_at,
    published_at: versionA.created_at,
    published_by: "human",
    evaluation_id: "evaluation-one",
    bench_verified: true,
    bench_passed: true,
    approval_id: "approval-one",
    publication_id: "publication-one",
    baseline_id: "baseline-one",
    regression_comparison_id: "comparison-one",
    current_baseline: false,
    active_assignment_count: 0,
    rollback_eligible: true,
    reason: "verified_historical_publication",
    limitations: [],
  };
  fixture.data.versions = [
    { ...versionA, registry },
    {
      ...versionA,
      id: "version-two",
      version_number: "2.0.0",
      payload_hash: "checksum-two",
      registry: {
        ...registry,
        version_id: "version-two",
        version_number: "2.0.0",
        current_baseline: true,
        active_assignment_count: 1,
        published_at: "2026-10-07T00:00:00Z",
      },
    },
  ];
  fixture.data.assignments = [
    {
      ...fixture.data.assignments[0],
      version_id: "version-two",
      current_transition_id: "activation-two",
      activation_verified: true,
      activation_history: [
        {
          transition_id: "activation-two",
          assignment_id: "assignment-a",
          generation: 1,
          to_version_id: "version-two",
          transition_type: "initial",
          actor_id: "human",
          reason: "Original activation",
          committed_at: versionA.created_at,
        },
      ],
    },
  ];
  fixture.data.permissions["agent:rollback"] = true;
  return fixture;
}

describe("AF-07 authoritative registry", () => {
  it("shows governance and preserves reviewed CAS and idempotency intent on failure/retry", async () => {
    const fixture = registryFixture();
    const act = vi
      .fn()
      .mockRejectedValueOnce(new Error("Conflict"))
      .mockResolvedValue({});
    render(<VersionRegistry {...fixture} blueprintId="agent-a" act={act} />);
    expect(screen.getAllByText("Known-good terverifikasi")).toHaveLength(2);
    expect(screen.getByText("Current Bench baseline")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Tinjau rollback/ }));
    const dialog = screen.getByRole("dialog", { name: "Rollback assignment" });
    expect(within(dialog).getByText("Current: v2.0.0")).toBeVisible();
    expect(within(dialog).getByText("Target: v1.0.0")).toBeVisible();
    expect(
      within(dialog).getByText("Publication: publication-one"),
    ).toBeVisible();
    const confirm = within(dialog).getByRole("button", {
      name: "Konfirmasi rollback assignment",
    });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Alasan rollback"), {
      target: { value: "Restore reviewed publication." },
    });
    fireEvent.click(confirm);
    await waitFor(() => expect(act).toHaveBeenCalledTimes(1));
    fireEvent.click(confirm);
    await waitFor(() => expect(act).toHaveBeenCalledTimes(2));
    expect(act.mock.calls[0]).toEqual(act.mock.calls[1]);
    expect(act.mock.calls[0][0]).toBe("/assignments/assignment-a/rollback");
    expect(act.mock.calls[0][1]).toMatchObject({
      target_version_id: "version-a",
      expected_current_version_id: "version-two",
      expected_transition_id: "activation-two",
      reason: "Restore reviewed publication.",
    });
    expect(act.mock.calls[0][1]).not.toHaveProperty("known_good");
  });
  it("denies rollback controls when server eligibility or permission is absent", () => {
    const fixture = registryFixture();
    fixture.data.versions[0].registry!.rollback_eligible = false;
    render(<VersionRegistry {...fixture} blueprintId="agent-a" />);
    expect(
      screen.getByRole("button", { name: /Tinjau rollback/ }),
    ).toBeDisabled();
  });
  it("historical run resolves captured version after the assignment pointer changes", () => {
    const fixture = registryFixture();
    const historical = historicalRunContext(fixture.data, "run-a");
    expect(historical.version?.id).toBe("version-a");
    expect(historical.assignment?.version_id).toBe("version-a");
    expect(fixture.data.assignments[0].version_id).toBe("version-two");
    fixture.data.runs[0].assignment_provenance_verified = false;
    expect(historicalRunContext(fixture.data, "run-a").version).toBeUndefined();
  });
});
