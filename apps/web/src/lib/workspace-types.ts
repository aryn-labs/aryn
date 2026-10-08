export type ResourceItem = {
  id: string;
  organization_id: string;
  project_id: string;
  name: string;
  created_at: string;
  status: string | null;
  slug: string | null;
  description: string | null;
  generation: number | null;
  verified: boolean | null;
  verification_reason: string | null;
  references: Record<string, unknown>;
};
export type ResourcePage = {
  organization_id: string;
  project_id: string;
  resource: string;
  items: ResourceItem[];
  next_cursor: string | null;
  limit: number;
  refreshed_at: string;
};
export type WorkspaceSummary = {
  organization_id: string;
  project_id: string;
  refreshed_at: string;
  metrics: Record<
    string,
    {
      value: number | null;
      definition: string;
      source: string;
      verification: "recorded_inventory" | "verified_bounded" | "unavailable";
    }
  >;
  permissions: Record<string, boolean>;
  attention: {
    code: string;
    count: number;
    description: string;
    route: string;
  }[];
  latest_runs: ResourceItem[];
  latest_audits: ResourceItem[];
  review_candidates: ResourceItem[];
  budget: {
    max_tokens_per_run: number;
    cumulative_tokens: number;
    reserved_tokens: number;
  } | null;
  usage: {
    availability: string;
    tokens: number | null;
    cost_usd: number | null;
    cost_source: string;
    entitlement: string;
    source: string;
  };
};
export const workspaceKey = (
  organization: string,
  project: string,
  resource: string,
  ...parameters: unknown[]
) => ["studio", organization, project, resource, ...parameters] as const;

export function routeIdentifier(value: string | undefined): string {
  try {
    return decodeURIComponent(value || "");
  } catch {
    return value || "";
  }
}
