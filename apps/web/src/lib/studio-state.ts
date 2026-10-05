import type { Evaluation, Runtime, Snapshot, Version } from "./types";

export function evaluationStatus(e: Evaluation) {
  if (
    !e.passed ||
    e.score < 1 ||
    e.total_scenarios < 1 ||
    e.passed_scenarios < e.total_scenarios
  )
    return "failed";
  return e.verified ? "bench_passed" : "bench_unverified";
}

export const needsApproval = (v: Version) =>
  v.status === "draft" && v.integrity_valid && v.bench_eligible;
export const runtimeTone = (runtime: Runtime) =>
  runtime.ready ? "success" : runtime.connected ? "warning" : "error";
export const availabilityLabel = {
  available: "Model tersedia",
  unknown: "Ketersediaan belum terverifikasi",
  unavailable: "Model tidak tersedia",
};

export function historicalRunContext(data: Snapshot, runId?: string) {
  const run = data.runs.find((r) => r.id === runId);
  const assignment = data.assignments.find((a) => a.id === run?.session_id);
  const version = data.versions.find(
    (v) =>
      v.id === assignment?.version_id &&
      v.blueprint_id === assignment.blueprint_id,
  );
  const blueprint = data.blueprints.find((b) => b.id === version?.blueprint_id);
  return { assignment, version, blueprint };
}
