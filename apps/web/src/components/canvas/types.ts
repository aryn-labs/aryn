export type NodeStatus =
  | "idle"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "blocked"
  | "waiting";

export type CanvasMode = "factory" | "execution" | "bench";

export type BaseNodeData = {
  id: string;
  label: string;
  sublabel?: string;
  nodeType:
    | "input"
    | "agent"
    | "model"
    | "knowledge"
    | "policy"
    | "approval"
    | "output"
    | "scenario"
    | "hermes"
    | "evaluation";
  status: NodeStatus;
  statusText?: string;
  badge?: string;
  badgeVariant?: "default" | "violet" | "cyan" | "emerald" | "amber" | "rose";
  metrics?: { label: string; value: string | number }[];
  details?: Record<string, unknown>;
  selected?: boolean;
  onSelectNode?: (nodeId: string) => void;
};
