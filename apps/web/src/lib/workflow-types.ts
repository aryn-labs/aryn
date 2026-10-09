export type Schema = "text" | "brief" | "content" | "website";
export type WorkflowNode = {
  id: string;
  label: string;
  kind: "start" | "agent" | "condition" | "handoff" | "review" | "end";
  input_schema: Schema;
  output_schema: Schema;
  assignment_id: string | null;
  agent_version_id: string | null;
  renderer: "static-document-v1" | null;
  predicate: {
    operator: "contains" | "equals" | "nonempty";
    literal: string;
  } | null;
};
export type WorkflowEdge = {
  id: string;
  source: string;
  target: string;
  source_port: "value" | "yes" | "no";
  target_port: "value";
};
export type Definition = {
  id: string;
  revision: number;
  name: string;
  graph: { nodes: WorkflowNode[]; edges: WorkflowEdge[] };
  positions: { id: string; x: number; y: number }[];
};
export type Version = {
  id: string;
  workflow_id: string;
  revision: number;
  digest: string;
  graph: Definition["graph"];
};
export type Task = {
  node_id: string;
  status: string;
  core_run_id: string | null;
  input_artifact_id: string | null;
  output_artifact_id: string | null;
};
export type WorkflowRun = {
  id: string;
  workflow_id: string;
  version_id: string;
  status: string;
  tasks: Task[];
  artifact_id: string | null;
  error_code: string | null;
};
export type Artifact = {
  id: string;
  digest: string;
  length: number;
  mime: string;
  schema_name: Schema;
  task_id: string;
  workflow_run_id: string;
  source_artifact_id: string | null;
  core_run_id: string | null;
  agent_version_id: string | null;
  model: string | null;
  validation: string;
  consumers: string[];
};
export type Deliverable = {
  id: string;
  workflow_run_id: string;
  artifact_id: string;
  digest: string;
  decision: string;
  reviewer: string;
  reason: string;
  created_at: string;
};
export type Page<T> = { items: T[]; next: string | null };
export function node(kind: WorkflowNode["kind"], id: string): WorkflowNode {
  return {
    id,
    label: id,
    kind,
    input_schema: "text",
    output_schema: "text",
    assignment_id: null,
    agent_version_id: null,
    renderer: null,
    predicate:
      kind === "condition" ? { operator: "nonempty", literal: "" } : null,
  };
}
export function emptyDefinition(): Definition {
  return {
    id: "",
    name: "Workflow baru",
    revision: 0,
    positions: [],
    graph: {
      nodes: [
        node("start", "input"),
        node("review", "review"),
        node("end", "output"),
      ],
      edges: [
        {
          id: "input_review",
          source: "input",
          target: "review",
          source_port: "value",
          target_port: "value",
        },
        {
          id: "review_output",
          source: "review",
          target: "output",
          source_port: "value",
          target_port: "value",
        },
      ],
    },
  };
}
export function documentGraph(
  research: { id: string; version_id: string },
  content: { id: string; version_id: string },
): Definition["graph"] {
  const nodes = [
    node("start", "input"),
    {
      ...node("agent", "research"),
      label: "Research",
      assignment_id: research.id,
      agent_version_id: research.version_id,
      output_schema: "brief" as Schema,
    },
    {
      ...node("handoff", "handoff"),
      input_schema: "brief" as Schema,
      output_schema: "brief" as Schema,
    },
    {
      ...node("agent", "content"),
      label: "Content",
      assignment_id: content.id,
      agent_version_id: content.version_id,
      input_schema: "brief" as Schema,
      output_schema: "content" as Schema,
    },
    {
      ...node("agent", "website"),
      label: "Website",
      renderer: "static-document-v1" as const,
      input_schema: "content" as Schema,
      output_schema: "website" as Schema,
    },
    {
      ...node("review", "review"),
      input_schema: "website" as Schema,
      output_schema: "website" as Schema,
    },
    {
      ...node("end", "output"),
      input_schema: "website" as Schema,
      output_schema: "website" as Schema,
    },
  ];
  return {
    nodes,
    edges: nodes.slice(1).map((n, i) => ({
      id: `edge_${i}`,
      source: nodes[i].id,
      target: n.id,
      source_port: "value",
      target_port: "value",
    })),
  };
}
