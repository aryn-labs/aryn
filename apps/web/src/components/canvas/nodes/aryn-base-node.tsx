import React from "react";
import { Handle, Position } from "@xyflow/react";
import {
  AlertTriangle,
  Bot,
  Brain,
  Check,
  CheckCircle2,
  Clock,
  Cpu,
  FileCode,
  Fingerprint,
  FlaskConical,
  Layers,
  LucideIcon,
  RotateCw,
  Send,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import type { BaseNodeData, NodeStatus } from "../types";

const iconMap: Record<string, LucideIcon> = {
  input: Send,
  agent: Bot,
  model: Cpu,
  knowledge: Brain,
  policy: ShieldCheck,
  approval: Fingerprint,
  output: FileCode,
  scenario: FlaskConical,
  hermes: Layers,
  evaluation: CheckCircle2,
};

function StatusIndicator({ status }: { status: NodeStatus }) {
  switch (status) {
    case "running":
      return (
        <span className="node-status-indicator status-running" title="Sedang berjalan">
          <RotateCw size={11} className="spin" />
        </span>
      );
    case "queued":
      return (
        <span className="node-status-indicator status-queued" title="Dalam antrean">
          <Clock size={11} />
        </span>
      );
    case "completed":
      return (
        <span className="node-status-indicator status-completed" title="Selesai">
          <Check size={11} />
        </span>
      );
    case "failed":
      return (
        <span className="node-status-indicator status-failed" title="Gagal">
          <XCircle size={11} />
        </span>
      );
    case "blocked":
      return (
        <span className="node-status-indicator status-blocked" title="Terblokir">
          <AlertTriangle size={11} />
        </span>
      );
    case "waiting":
      return (
        <span className="node-status-indicator status-waiting" title="Menunggu persetujuan">
          <Clock size={11} />
        </span>
      );
    default:
      return null;
  }
}

export function ArynBaseNode({
  data,
  selected,
  hasTarget = true,
  hasSource = true,
  targetPosition = Position.Left,
  sourcePosition = Position.Right,
  children,
}: {
  data: BaseNodeData;
  selected?: boolean;
  hasTarget?: boolean;
  hasSource?: boolean;
  targetPosition?: Position;
  sourcePosition?: Position;
  children?: React.ReactNode;
}) {
  const Icon = iconMap[data.nodeType] || Bot;
  const isSelected = selected || data.selected;

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.onSelectNode) {
      data.onSelectNode(data.id);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (data.onSelectNode) {
        data.onSelectNode(data.id);
      }
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      className={`aryn-node aryn-node-${data.nodeType} status-${data.status} ${
        isSelected ? "node-selected" : ""
      }`}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      aria-label={`Node ${data.label}: ${data.statusText || data.status}`}
    >
      {hasTarget && (
        <Handle
          type="target"
          position={targetPosition}
          className="aryn-handle aryn-handle-target"
        />
      )}

      <div className="aryn-node-header">
        <div className="aryn-node-icon-wrap">
          <Icon size={14} className="aryn-node-icon" />
        </div>
        <div className="aryn-node-title-group">
          <span className="aryn-node-label">{data.label}</span>
          {data.sublabel && (
            <span className="aryn-node-sublabel">{data.sublabel}</span>
          )}
        </div>
        <StatusIndicator status={data.status} />
      </div>

      {data.badge && (
        <div className="aryn-node-badge-row">
          <span
            className={`aryn-node-badge badge-${data.badgeVariant || "default"}`}
          >
            {data.badge}
          </span>
          {data.statusText && (
            <span className="aryn-node-status-text">{data.statusText}</span>
          )}
        </div>
      )}

      {children && <div className="aryn-node-body">{children}</div>}

      {data.metrics && data.metrics.length > 0 && (
        <div className="aryn-node-metrics">
          {data.metrics.map((metric, i) => (
            <div key={i} className="aryn-node-metric-item">
              <span className="metric-label">{metric.label}</span>
              <span className="metric-val mono">{metric.value}</span>
            </div>
          ))}
        </div>
      )}

      {hasSource && (
        <Handle
          type="source"
          position={sourcePosition}
          className="aryn-handle aryn-handle-source"
        />
      )}
    </div>
  );
}
