import type {
  Evaluation,
  Runtime,
  Snapshot,
  Version,
  Workspace,
} from "./types";

export function evaluationStatus(e: Evaluation) {
  const policy =
    e.provenance?.evidence_format === 2 ? e.provenance.quality_gate : undefined;
  const threshold = policy?.min_score_threshold ?? 1;
  const consistent =
    e.total_scenarios > 0 &&
    e.passed_scenarios >= 0 &&
    e.passed_scenarios <= e.total_scenarios &&
    Number.isFinite(e.score) &&
    Math.abs(
      e.score -
        Math.round((e.passed_scenarios / e.total_scenarios) * 10000) / 10000,
    ) < 0.00001;
  if (
    !e.passed ||
    !consistent ||
    e.score < threshold ||
    (policy && !policy.passed)
  )
    return "failed";
  return e.verified ? "bench_passed" : "bench_unverified";
}

export const needsApproval = (v: Version) =>
  v.status === "draft" &&
  v.integrity_valid &&
  v.bench_eligible &&
  !v.regression?.promotion_blocked;
export const runtimeTone = (runtime: Runtime) =>
  runtime.ready ? "success" : runtime.connected ? "warning" : "error";

export const executionReady = (workspace: Workspace) =>
  workspace.runtime.ready &&
  workspace.gateway.connected &&
  workspace.gateway.discovery_valid &&
  workspace.gateway.runtime_binding_verified;

export const gatewayStatus = (workspace: Workspace) =>
  !workspace.gateway.connected
    ? {
        tone: "error" as const,
        label: "Model Gateway tidak dapat dijangkau.",
      }
    : !workspace.gateway.discovery_valid
      ? {
          tone: "warning" as const,
          label: "Discovery Model Gateway belum dapat diverifikasi.",
        }
      : !workspace.gateway.runtime_binding_verified
        ? {
            tone: "warning" as const,
            label:
              "Model Gateway terhubung; routing ARYN Runtime belum terverifikasi.",
          }
        : { tone: "success" as const, label: "Model Gateway terhubung" };
export const availabilityLabel = {
  available: "Model tersedia",
  unknown: "Ketersediaan belum terverifikasi",
  unavailable: "Model tidak tersedia",
};

export function historicalRunContext(data: Snapshot, runId?: string) {
  const run = data.runs.find((r) => r.id === runId);
  const currentAssignment = data.assignments.find(
    (a) => a.id === (run?.assignment_id || run?.session_id),
  );
  const version = data.versions.find(
    (v) =>
      run?.assignment_provenance_verified &&
      v.id === run.agent_version_id &&
      v.payload_hash === run.agent_payload_hash,
  );
  const assignment =
    currentAssignment && version
      ? {
          ...currentAssignment,
          version_id: version.id,
          current_transition_id: run?.assignment_transition_id,
        }
      : undefined;
  const blueprint = data.blueprints.find((b) => b.id === version?.blueprint_id);
  return { assignment, version, blueprint };
}
