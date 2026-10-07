export type OutputContract = {
  format?: string;
  schema_definition?: Record<string, unknown> | null;
  required_sections?: string[];
  description?: string | null;
  strict?: boolean;
};

export type Constraints = {
  disallowed_actions?: string[];
  operational_rules?: string[];
  require_evidence_citation?: boolean;
  max_execution_time_seconds?: number;
};

export type ToolPolicy = {
  tool_grants?: string[];
  forbidden_tools?: string[];
  deny_by_default?: boolean;
  network_access?: boolean;
  file_write_access?: boolean;
  code_execution?: boolean;
};

export type ModelPolicy = {
  primary_model?: string;
  provider?: string;
  allowed_models?: string[];
  temperature?: number;
  max_tokens?: number;
  allow_fallback?: boolean;
  stop_sequences?: string[];
};

export type BudgetPolicy = {
  max_tokens_per_run?: number;
  max_turns?: number;
  max_cost_usd?: number;
  timeout_seconds?: number;
};

export type EvaluationReference = {
  suite_id?: string;
  evaluation_version?: string;
  min_score_threshold?: number;
  required_scenarios?: string[];
  evaluation_id?: string | null;
};

export type Blueprint = {
  id: string;
  name: string;
  slug: string;
  description: string;
  role?: string | null;
  objective?: string | null;
  owner?: string | null;
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
  regression?: RegressionComparison | null;
  created_at: string;
  schema_version?: string;
  role?: string;
  objective?: string;
  owner?: string | null;
  output_contract?: OutputContract;
  constraints?: Constraints;
  tool_policy?: ToolPolicy;
  model_policy?: ModelPolicy;
  budget_policy?: BudgetPolicy;
  evaluation_reference?: EvaluationReference;
};
export type EvaluationState =
  | "passed"
  | "failed"
  | "policy_violation"
  | "unverifiable"
  | "invalid_evidence"
  | "runtime_error";
export type GraderResult = {
  grader_id: string;
  grader_type: string;
  grader_version: string;
  state: EvaluationState;
  passed: boolean;
  reason: string;
  details: Record<string, unknown>;
};
export type ScenarioDefinition = {
  scenario_id: string;
  name: string;
  category: string;
};
export type EvaluationSuite = {
  suite_id: string;
  evaluation_version: string;
  aliases: string[];
  name: string;
  scenarios: ScenarioDefinition[];
};
export type Scenario = {
  scenario_version?: string;
  state?: EvaluationState;
  grader_results?: GraderResult[];
  execution?: Record<string, unknown>;
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
  regression?: RegressionComparison | null;
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
    suite_id?: string;
    suite_hash?: string;
    runtime_adapter?: string;
    evidence_format?: number;
    state?: EvaluationState;
    suite_aggregate?: {
      passed: boolean;
      total_scenarios: number;
      passed_scenarios: number;
      score: number;
      state: EvaluationState;
    };
    evaluation_reference?: EvaluationReference;
    quality_gate?: {
      passed: boolean;
      reason: string;
      min_score_threshold: number;
      required_scenarios: string[];
    };
    evaluation_version: string;
    requested_model: string;
    payload_hash: string;
  };
};
// POST /versions/:id/bench JSON and SSE bench.completed share this contract.
export type BenchCompletion = {
  evaluation_id: string;
  version_id: string;
  evaluation: Evaluation;
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
  accepted_baselines?: AcceptedBaseline[];
  evaluation_suites?: EvaluationSuite[];
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

export type EvaluationIdentity = {
  evaluation_id: string;
  version_id: string;
  version_number: string;
  payload_hash: string;
  evidence_hash: string;
  evidence_format: 1 | 2;
};
export type AcceptedBaseline = {
  baseline_id: string;
  blueprint_id: string;
  generation: number;
  evaluation: EvaluationIdentity;
  suite_id: string;
  evaluation_version: string;
  suite_hash: string;
  accepted_by: string;
  accepted_at: string;
  acceptance: string;
  reason: string;
  supersedes_id?: string | null;
  limitations: string[];
};
export type RegressionFinding = {
  kind: string;
  reason: string;
  critical: boolean;
  scenario_id?: string | null;
  grader_id?: string | null;
  baseline_state?: EvaluationState | null;
  candidate_state?: EvaluationState | null;
  details: Record<string, unknown>;
};
export type RegressionComparison = {
  comparison_id: string;
  blueprint_id: string;
  baseline_id?: string | null;
  baseline?: EvaluationIdentity | null;
  candidate: EvaluationIdentity;
  suite_id: string;
  evaluation_version: string;
  suite_hash: string;
  compared_at: string;
  state:
    | "bootstrap"
    | "baseline_required"
    | "comparable"
    | "incompatible"
    | "invalid"
    | "unverifiable";
  reason: string;
  promotion_blocked: boolean;
  baseline_score?: number | null;
  candidate_score?: number | null;
  score_delta?: number | null;
  scenarios: {
    scenario_id: string;
    scenario_version: string;
    baseline_state: EvaluationState;
    candidate_state: EvaluationState;
    regression: boolean;
    critical: boolean;
    graders: {
      grader_id: string;
      grader_type: string;
      grader_version: string;
      baseline_state: EvaluationState;
      candidate_state: EvaluationState;
      candidate_reason: string;
      regression: boolean;
      critical: boolean;
    }[];
  }[];
  metrics: Record<
    string,
    {
      state: "comparable" | "unavailable" | "invalid";
      baseline?: number | null;
      candidate?: number | null;
      delta?: number | null;
    }
  >;
  regressions: RegressionFinding[];
  critical_regressions: RegressionFinding[];
  limitations: string[];
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
