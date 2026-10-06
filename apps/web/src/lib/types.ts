export type Blueprint = {
  id: string;
  name: string;
  slug: string;
  description: string;
  created_at: string;
};
export type Version = {
  id: string;
  blueprint_id: string;
  version_number: string;
  status: string;
  system_prompt: string;
  model: string;
  temperature: number;
  max_tokens: number;
  payload_hash: string;
  evaluation_id?: string;
  integrity_valid: boolean;
  bench_eligible: boolean;
  governance_valid: boolean;
  created_at: string;
};
export type Scenario = {
  scenario_id: string;
  name: string;
  category: string;
  passed: boolean;
  score: number;
  actual_output: string;
  latency_seconds: number;
  failure_reason?: string;
  actual_model: string;
  total_tokens: number;
};
export type Evaluation = {
  id: string;
  blueprint_id: string;
  version_id: string;
  passed: number;
  verified: boolean;
  total_scenarios: number;
  passed_scenarios: number;
  score: number;
  details: Scenario[];
  evaluated_at: string;
  provenance: {
    evaluation_version: string;
    requested_model: string;
    payload_hash: string;
  };
};
export type Assignment = {
  id: string;
  blueprint_id: string;
  version_id: string;
  role_name: string;
  status: string;
  project_id: string;
  created_at: string;
};
export type Approval = {
  id: string;
  target_id: string;
  payload_hash: string;
  approved_by: string;
  verified: boolean;
  evaluation_id?: string;
  comments: string;
  created_at: string;
  status: string;
};
export type Run = {
  id: string;
  status: string;
  prompt: string;
  output: string;
  model: string;
  provider: string;
  total_tokens: number;
  actual_model?: string | null;
  gateway?: "9Router" | null;
  runtime_backend?: "Hermes" | null;
  actual_provider?: string | null;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
  completed_at?: string;
  error_message?: string;
  session_id: string;
};
export type Audit = {
  id: string;
  event_type: string;
  resource_id: string;
  status: string;
  occurred_at: string;
  actor_id: string;
  correlation_id: string;
  redacted_payload: Record<string, unknown>;
  integrity_reference: string;
};
export type Snapshot = {
  blueprints: Blueprint[];
  versions: Version[];
  evaluations: Evaluation[];
  assignments: Assignment[];
  approvals: Approval[];
  runs: Run[];
  audit: Audit[];
  permissions: Record<string, boolean>;
  budget: { max_tokens_per_run: number; cumulative_tokens: number };
};
export type Runtime = {
  connected: boolean;
  ready: boolean;
  version?: string;
  message: string;
  enabled_toolsets?: string[];
  readiness?: string;
  reason?: string;
};
export type Workspace = {
  organization: { id: string; name: string };
  projects: { id: string; name: string }[];
  user: { name: string; id: string; role: string };
  models: {
    model_id: string;
    display_name: string;
    provider: string;
    availability: "available" | "unavailable" | "unknown";
    availability_reason: string;
    availability_source: string;
  }[];
  runtime: Runtime;
  gateway: {
    name: "9Router";
    connected: boolean;
    discovery_valid: boolean;
    runtime_binding_verified: boolean;
    reason: string;
  };
  mode: string;
};

export type Shared = {
  data: Snapshot;
  workspace: Workspace;
  project: string;
  pending: boolean;
  error?: string;
  resetError: () => void;
  act: (
    path: string,
    body: unknown,
    success: string,
  ) => Promise<Record<string, unknown>>;
  actStream?: (
    path: string,
    body: unknown,
    success: string,
    onEvent?: (event: { type: string; data: any }) => void,
  ) => Promise<any>;
  openBlueprint: () => void;
};
