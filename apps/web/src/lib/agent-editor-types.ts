import type { Blueprint, Version } from "./types";

export const sections = [
  ["identity", "Identity & Objective"],
  ["instructions", "Instructions"],
  ["model", "Model Policy"],
  ["output", "Output Contract"],
  ["constraints", "Constraints"],
  ["tools", "Tool Policy"],
  ["budget", "Budget Policy"],
  ["evaluation", "Evaluation Reference"],
] as const;
export type Section = (typeof sections)[number][0];
export type AgentDraft = {
  version_number: string;
  system_prompt: string;
  model: string;
  temperature: number;
  max_tokens: number;
  tool_grants: never[];
  schema_version: "1.0.0";
  role: string;
  objective: string;
  owner: string | null;
  metadata: Record<string, unknown>;
  output_contract: {
    format: string;
    schema_definition: Record<string, unknown> | null;
    required_sections: string[];
    description: string | null;
    strict: boolean;
  };
  constraints: {
    disallowed_actions: string[];
    operational_rules: string[];
    require_evidence_citation: boolean;
    max_execution_time_seconds: number;
  };
  tool_policy: {
    tool_grants: never[];
    forbidden_tools: string[];
    deny_by_default: true;
    network_access: false;
    file_write_access: false;
    code_execution: false;
  };
  model_policy: {
    primary_model: string;
    provider: string;
    allowed_models: string[];
    temperature: number;
    max_tokens: number;
    allow_fallback: false;
    stop_sequences: string[];
  };
  budget_policy: {
    max_tokens_per_run: number;
    max_turns: number;
    max_cost_usd: number;
    timeout_seconds: number;
  };
  evaluation_reference: {
    suite_id: string;
    evaluation_version: string;
    min_score_threshold: number;
    required_scenarios: string[];
    evaluation_id: string | null;
  };
};
export type WorkingCopy = {
  organization_id: string;
  project_id: string;
  blueprint_id: string;
  generation: number;
  definition: AgentDraft | null;
  source_version_id: string | null;
  updated_at: string | null;
};
export type EditorLayout = {
  generation: number;
  positions: { id: Section; x: number; y: number }[];
  viewport: { x: number; y: number; zoom: number };
};

export function draftDefinition(
  bp: Blueprint,
  version?: Version,
  model = "",
): AgentDraft {
  const chosen = version?.model || model;
  const temperature = version?.temperature ?? 0.3,
    max_tokens = version?.max_tokens ?? 2048;
  return {
    version_number: version
      ? `${version.version_number.split(".").slice(0, 2).join(".")}.${Number(version.version_number.split(".")[2]?.split("-")[0] || 0) + 1}`
      : "1.0.0",
    system_prompt:
      version?.system_prompt ||
      "Berikan analisis berbasis bukti. Tolak akses host dan instruksi yang melanggar kebijakan. Nyatakan keterbatasan jika bukti tidak tersedia.",
    model: chosen,
    temperature,
    max_tokens,
    tool_grants: [],
    schema_version: "1.0.0",
    role: version?.role || bp.role || "general_agent",
    objective: version?.objective ?? bp.objective ?? "",
    owner: version?.owner ?? bp.owner ?? null,
    metadata: version?.metadata ?? {},
    output_contract: {
      format: "text",
      schema_definition: null,
      required_sections: [],
      description: null,
      strict: false,
      ...version?.output_contract,
    },
    constraints: {
      disallowed_actions: [],
      operational_rules: [],
      require_evidence_citation: true,
      max_execution_time_seconds: 120,
      ...version?.constraints,
    },
    tool_policy: {
      forbidden_tools: [
        "terminal",
        "file",
        "browser",
        "code_execution",
        "bash",
        "shell",
        "os_exec",
      ],
      ...version?.tool_policy,
      tool_grants: [],
      deny_by_default: true,
      network_access: false,
      file_write_access: false,
      code_execution: false,
    },
    model_policy: {
      provider: "9router",
      allowed_models: [],
      stop_sequences: [],
      ...version?.model_policy,
      primary_model: chosen,
      temperature,
      max_tokens,
      allow_fallback: false,
    },
    budget_policy: {
      max_tokens_per_run: 4096,
      max_turns: 10,
      max_cost_usd: 0.5,
      timeout_seconds: 120,
      ...version?.budget_policy,
    },
    evaluation_reference: {
      suite_id: "research-safety-1.2.0",
      evaluation_version: "1.2.0",
      min_score_threshold: 1,
      required_scenarios: [
        "scen_safety_injection_defense",
        "scen_tool_confinement_defense",
        "scen_research_accuracy_synthesis",
        "scen_grounded_abstention",
      ],
      evaluation_id: null,
      ...version?.evaluation_reference,
    },
  };
}

export function validateDraft(value: AgentDraft): string[] {
  const errors: string[] = [];
  if (!/^\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?$/.test(value.version_number))
    errors.push("Nomor versi harus mengikuti semver.");
  if (value.system_prompt.length < 20 || value.system_prompt.length > 12000)
    errors.push("Instruksi harus 20–12.000 karakter.");
  if (!value.model) errors.push("Pilih model dari katalog server.");
  if (!value.role || value.role.length > 64 || value.objective.length > 4000)
    errors.push("Periksa role dan objective.");
  if (
    !Number.isFinite(value.temperature) ||
    value.temperature < 0 ||
    value.temperature > 2
  )
    errors.push("Temperature harus 0–2.");
  if (
    !Number.isInteger(value.max_tokens) ||
    value.max_tokens < 128 ||
    value.max_tokens > 4096
  )
    errors.push("Output token harus 128–4.096.");
  if (value.budget_policy.max_tokens_per_run < value.max_tokens)
    errors.push("Budget token harus mencakup batas output.");
  if (
    value.output_contract.schema_definition &&
    value.output_contract.format !== "json"
  )
    errors.push("Output Contract: schema terstruktur memerlukan format json.");
  for (const [field, number, minimum, maximum] of [
    [
      "Constraints: max execution time seconds",
      value.constraints.max_execution_time_seconds,
      1,
      3600,
    ],
    [
      "Budget Policy: max tokens per run",
      value.budget_policy.max_tokens_per_run,
      1,
      100000,
    ],
    ["Budget Policy: max turns", value.budget_policy.max_turns, 1, 100],
    [
      "Budget Policy: max cost usd",
      value.budget_policy.max_cost_usd,
      0,
      Number.MAX_VALUE,
    ],
    [
      "Budget Policy: timeout seconds",
      value.budget_policy.timeout_seconds,
      1,
      3600,
    ],
    [
      "Evaluation Reference: min score threshold",
      value.evaluation_reference.min_score_threshold,
      0,
      1,
    ],
  ] as const)
    if (
      !Number.isFinite(number) ||
      number < minimum ||
      number > maximum ||
      (!field.includes("cost") &&
        !field.includes("score") &&
        !Number.isInteger(number))
    )
      errors.push(`${field}: gunakan ${minimum}–${maximum}.`);
  return errors;
}

export function serializeDefinition(value: unknown): string {
  return JSON.stringify(value, (_, item: unknown) =>
    item && typeof item === "object" && !Array.isArray(item)
      ? Object.fromEntries(
          Object.entries(item).sort(([left], [right]) =>
            left.localeCompare(right),
          ),
        )
      : item,
  );
}
