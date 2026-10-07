import type { Shared, Version } from "../lib/types";

export const versionA: Version = {
  id: "version-a",
  blueprint_id: "agent-a",
  version_number: "1.0.0",
  status: "published",
  system_prompt: "Instruksi historis khusus Agent A.",
  model: "model-a",
  temperature: 0.3,
  max_tokens: 512,
  payload_hash: "display-only-hash-a",
  integrity_valid: true,
  bench_eligible: true,
  governance_valid: true,
  created_at: "2026-10-06T00:00:00Z",
};
// Component-only fixtures. API/browser lifecycle tests execute the real Bench.
export function studioFixture(): Shared {
  return {
    project: "project-b",
    pending: false,
    resetError: () => {},
    openBlueprint: () => {},
    act: async () => ({}),
    workspace: {
      gateway: {
        name: "9Router",
        connected: true,
        discovery_valid: true,
        runtime_binding_verified: true,
        reason: "isolated-test",
      },
      organization: { id: "org", name: "ARYN" },
      projects: [
        { id: "project-a", name: "Proyek Pertama" },
        { id: "project-b", name: "Proyek Aktif" },
      ],
      user: { id: "user", name: "Pemilik", role: "admin" },
      mode: "isolated-test",
      runtime: {
        connected: false,
        ready: false,
        message: "ARYN Runtime tidak tersedia",
      },
      models: ["model-a", "model-b"].map((model_id) => ({
        model_id,
        display_name: model_id,
        provider: "isolated",
        availability: "available",
        availability_reason: "test",
        availability_source: "isolated-test",
      })),
    },
    data: {
      blueprints: [
        {
          id: "agent-a",
          name: "Agent A",
          slug: "agent-a",
          description: "",
          created_at: versionA.created_at,
        },
        {
          id: "agent-b",
          name: "Agent B",
          slug: "agent-b",
          description: "",
          created_at: versionA.created_at,
        },
      ],
      versions: [
        versionA,
        {
          ...versionA,
          id: "version-b",
          blueprint_id: "agent-b",
          version_number: "2.0.0",
          system_prompt: "Instruksi baru Agent B.",
          model: "model-b",
        },
      ],
      assignments: ["a", "b"].map((id) => ({
        id: `assignment-${id}`,
        blueprint_id: `agent-${id}`,
        version_id: `version-${id}`,
        role_name: `Peneliti ${id}`,
        status: "active",
        project_id: "project-b",
        created_at: versionA.created_at,
      })),
      runs: [
        {
          id: "run-a",
          session_id: "assignment-a",
          status: "completed",
          prompt: "Riset Agent A",
          assignment_id: "assignment-a",
          agent_version_id: versionA.id,
          agent_payload_hash: versionA.payload_hash,
          assignment_provenance_verified: true,
          output: "Hasil historis A",
          model: "model-a",
          provider: "isolated",
          total_tokens: 30,
          input_tokens: 20,
          output_tokens: 10,
          created_at: versionA.created_at,
        },
      ],
      evaluations: [],
      approvals: [],
      audit: [],
      permissions: {
        "run:create": true,
        "version:approve": true,
        "version:publish": true,
      },
      budget: { max_tokens_per_run: 1000, cumulative_tokens: 30 },
    },
  };
}
