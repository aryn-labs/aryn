import type { ComponentType } from "react";
import { ArynBaseNode } from "./aryn-base-node";
import type { BaseNodeData } from "../types";

export function InputNode({ data, selected }: any) {
  const nodeData = data as BaseNodeData;
  const hasPrompt = Boolean(nodeData.details?.prompt);
  const promptLength = hasPrompt ? String(nodeData.details?.prompt).length : 0;
  return (
    <ArynBaseNode data={nodeData} selected={selected} hasTarget={false}>
      {hasPrompt ? (
        <div className="node-snippet">
          <small>Status Masukan:</small>
          <div className="node-stat-value">
            {promptLength} karakter terkonfigurasi
          </div>
        </div>
      ) : null}
    </ArynBaseNode>
  );
}

export function AgentNode({ data, selected }: any) {
  const nodeData = data as BaseNodeData;
  return (
    <ArynBaseNode data={nodeData} selected={selected}>
      {nodeData.details?.systemPrompt ? (
        <div className="node-snippet">
          <small>Instruksi Sistem:</small>
          <div className="node-stat-value">
            {String(nodeData.details.systemPrompt).length > 60
              ? `${String(nodeData.details.systemPrompt).slice(0, 50)}…`
              : String(nodeData.details.systemPrompt)}
          </div>
        </div>
      ) : null}
    </ArynBaseNode>
  );
}

export function ModelNode({ data, selected }: any) {
  const nodeData = data as BaseNodeData;
  return (
    <ArynBaseNode data={nodeData} selected={selected}>
      {nodeData.details?.model ? (
        <div className="node-code-badge mono">
          {String(nodeData.details.model)}
        </div>
      ) : null}
    </ArynBaseNode>
  );
}

export function KnowledgeNode({ data, selected }: any) {
  const nodeData = data as BaseNodeData;
  return (
    <ArynBaseNode data={nodeData} selected={selected}>
      <div className="node-text-subtle">
        Konteks versi dan proyek · Bukan sumber data eksternal
      </div>
    </ArynBaseNode>
  );
}

export function PolicyNode({ data, selected }: any) {
  const nodeData = data as BaseNodeData;
  return (
    <ArynBaseNode data={nodeData} selected={selected}>
      <div className="node-text-subtle">
        {nodeData.details?.policyText
          ? String(nodeData.details.policyText)
          : "Batas keamanan Core · Zero host toolset"}
      </div>
    </ArynBaseNode>
  );
}

export function ApprovalNode({ data, selected }: any) {
  const nodeData = data as BaseNodeData;
  return (
    <ArynBaseNode data={nodeData} selected={selected}>
      {nodeData.details?.hash ? (
        <div className="node-hash mono">
          <small>SHA-256:</small> {String(nodeData.details.hash).slice(0, 12)}…
        </div>
      ) : null}
    </ArynBaseNode>
  );
}

export function OutputNode({ data, selected }: any) {
  const nodeData = data as BaseNodeData;
  const hasOutput = Boolean(nodeData.details?.output);
  const outputLength = hasOutput ? String(nodeData.details?.output).length : 0;
  return (
    <ArynBaseNode data={nodeData} selected={selected} hasSource={false}>
      {hasOutput ? (
        <div className="node-snippet">
          <small>Hasil Output:</small>
          <div className="node-stat-value">
            {outputLength} karakter dihasilkan
          </div>
        </div>
      ) : null}
    </ArynBaseNode>
  );
}

export function ScenarioNode({ data, selected }: any) {
  const nodeData = data as BaseNodeData;
  return (
    <ArynBaseNode data={nodeData} selected={selected} hasTarget={false}>
      {nodeData.details?.category ? (
        <div className="node-text-subtle">
          Kategori: {String(nodeData.details.category)}
        </div>
      ) : null}
    </ArynBaseNode>
  );
}

export function HermesNode({ data, selected }: any) {
  const nodeData = data as BaseNodeData;
  return (
    <ArynBaseNode data={nodeData} selected={selected}>
      <div className="node-text-subtle">
        Adapter teks · trace per-node belum tersedia
      </div>
    </ArynBaseNode>
  );
}

export function EvaluationNode({ data, selected }: any) {
  const nodeData = data as BaseNodeData;
  return (
    <ArynBaseNode data={nodeData} selected={selected} hasSource={false}>
      {nodeData.details?.summary ? (
        <div className="node-eval-summary">
          <strong>{String(nodeData.details.summary)}</strong>
        </div>
      ) : null}
    </ArynBaseNode>
  );
}

export const nodeTypes: Record<string, ComponentType<any>> = {
  arynInput: InputNode,
  input: InputNode,
  agent: AgentNode,
  model: ModelNode,
  knowledge: KnowledgeNode,
  policy: PolicyNode,
  approval: ApprovalNode,
  arynOutput: OutputNode,
  output: OutputNode,
  scenario: ScenarioNode,
  hermes: HermesNode,
  evaluation: EvaluationNode,
};
