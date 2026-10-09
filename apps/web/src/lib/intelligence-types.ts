export type Page<T> = { items: T[]; next: string | null };
export const evidenceStatuses = [
  "SUPPORTED",
  "CONFLICTING",
  "INSUFFICIENT_EVIDENCE",
  "NOT_FOUND",
] as const;
export const incidentStatuses = [
  "OPEN",
  "INVESTIGATING",
  "PROPOSED",
  "EXECUTING",
  "DEGRADED",
  "RECOVERED",
  "CLOSED",
  "OUTCOME_UNKNOWN",
] as const;
export type SourceRef = {
  kind: "artifact" | "run" | "demo_observation" | "document";
  id: string;
};
export type Source = {
  id: string;
  title: string;
  source_ref: SourceRef;
  source_digest: string;
  digest: string;
  observed_at: string;
  collected_at: string;
  sanitized: boolean;
  quality: string;
  max_age_seconds: number;
};
export type EvidenceItem = {
  source_id: string;
  relationship: "support" | "conflict" | "neutral";
  integrity: "VERIFIED" | "UNVERIFIED";
  freshness: string;
  excerpt: string;
  reason: string;
  observed_at: string | null;
  collected_at: string | null;
};
export type Bundle = {
  id: string;
  title: string;
  created_at: string;
  digest: string;
  status: string;
  hypothesis: {
    question: string;
    predicate: string;
    text: string;
    minimum_sources: number;
    target_id?: string | null;
  };
  source_ids: string[];
  workflow: { id: string; workflow_id: string; version_id: string } | null;
  evaluation: {
    status: string;
    abstention: string | null;
    coverage: number;
    required_coverage: number;
    evaluated_at: string;
    items: EvidenceItem[];
  };
};
export type Fixture = {
  id: string;
  name: string;
  revision: number;
  running: boolean;
  blocking_fault: boolean;
  disposable: true;
  updated_at: string;
};
export type TimelineEvent = {
  id: string;
  sequence: number;
  event: string;
  from_status: string | null;
  to_status: string;
  actor_id: string;
  reference_id: string | null;
  created_at: string;
};
export type Proposal = {
  id: string;
  payload_hash: string;
  target_id: string;
  target_revision: number;
  action: "restart_demo";
  parameters: Record<string, never>;
  reversible_intent: string;
  preconditions: string;
  verification: {
    kind: string;
    require_running: true;
    require_no_blocking_fault: true;
  };
  reason: string;
  bundle_id: string;
  bundle_digest: string;
};
export type Capsule = {
  id: string;
  incident_id: string;
  bundle_id: string;
  digest: string;
  sanitized: true;
  snapshot: { running: boolean; blocking_fault: boolean };
  scenario_id: string;
  scenario_version: string;
  created_at: string;
};
export type Incident = {
  id: string;
  title: string;
  status: string;
  severity: string;
  owner_id: string;
  revision: number;
  created_at: string;
  updated_at: string;
  target_id: string;
  signal_id: string;
  bundle_id: string | null;
  capsule_id: string | null;
};
export type IncidentDetail = Incident & {
  fixture: Fixture;
  signal: {
    id: string;
    source_id: string;
    dedup_key: string;
    demo: true;
    created_at: string;
  };
  timeline: TimelineEvent[];
  bundle: Bundle | null;
  proposal: Proposal | null;
  approval: {
    approval_id: string;
    approved_by: string;
    payload_hash: string;
    created_at: string;
  } | null;
  execution: {
    id: string;
    status: string;
    before_revision: number;
    after_revision: number | null;
    error_code: string | null;
    approval: {
      approval_id: string;
      approved_by: string;
      payload_hash: string;
    };
  } | null;
  verification: {
    id: string;
    recovered: boolean;
    observation_id: string;
    target_revision: number;
    digest: string;
  } | null;
  capsule: Capsule | null;
};
export type Replay = {
  id: string;
  capsule_id: string;
  capsule_digest: string;
  scenario_id: string;
  scenario_version: string;
  backend: "deterministic_in_memory";
  model: null;
  provider: null;
  passed: boolean;
  live_write_calls: 0;
  promotion_evidence: false;
  digest: string;
  created_at: string;
  graders: {
    grader_id: string;
    passed: boolean;
    reason: string;
    [key: string]: unknown;
  }[];
};
