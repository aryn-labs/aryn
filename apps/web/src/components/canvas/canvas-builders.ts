import type { Node, Edge } from "@xyflow/react";
import type { Blueprint, Evaluation, Run, Version, Workspace } from "../../lib/types";
import { scenarioNames } from "../shared";

export function buildFactoryNodesAndEdges(
  blueprint: Blueprint,
  version?: Version | null,
  workspace?: Workspace,
): { nodes: Node[]; edges: Edge[] } {
  const isPublished = version?.status === "published";
  const isApproved = version?.status === "approved" || isPublished;
  const isBenchPassed = Boolean(version?.bench_eligible);
  const modelAvailability =
    workspace?.models.find((m) => m.model_id === version?.model)?.availability || "unknown";

  const nodes: Node[] = [
    {
      id: "node-input",
      type: "arynInput",
      position: { x: 40, y: 160 },
      data: {
        id: "node-input",
        label: "User Input",
        sublabel: "Parameter & Query Riset",
        nodeType: "input",
        status: "idle",
        badge: "Teks / Instruksi",
        badgeVariant: "default",
      },
    },
    {
      id: "node-agent",
      type: "agent",
      position: { x: 320, y: 160 },
      data: {
        id: "node-agent",
        label: blueprint.name,
        sublabel: version ? `Versi v${version.version_number}` : "Draft Baru",
        nodeType: "agent",
        status: "idle",
        badge: version?.status || "Draft",
        badgeVariant: isPublished ? "emerald" : "violet",
        details: {
          systemPrompt: version?.system_prompt || "Instruksi agen belum dikonfigurasi.",
        },
      },
    },
    {
      id: "node-model",
      type: "model",
      position: { x: 600, y: 160 },
      data: {
        id: "node-model",
        label: version?.model || "Model Belum Dipilih",
        sublabel: "Router Hermes",
        nodeType: "model",
        status: modelAvailability === "unavailable" ? "blocked" : "idle",
        badge: version ? `${version.temperature} temp` : "0.3 temp",
        badgeVariant: modelAvailability === "available" ? "cyan" : "amber",
        statusText: modelAvailability === "available" ? "Tersedia" : "Model dibatasi",
        metrics: [
          {
            label: "Maks Token",
            value: version?.max_tokens || 512,
          },
        ],
        details: {
          model: version?.model,
          temperature: version?.temperature,
          maxTokens: version?.max_tokens,
          availability: modelAvailability,
        },
      },
    },
    {
      id: "node-knowledge",
      type: "knowledge",
      position: { x: 880, y: 80 },
      data: {
        id: "node-knowledge",
        label: "Konteks & Batasan",
        sublabel: "Cakupan Proyek",
        nodeType: "knowledge",
        status: "idle",
        badge: "Host Confinement",
        badgeVariant: "cyan",
      },
    },
    {
      id: "node-policy",
      type: "policy",
      position: { x: 880, y: 240 },
      data: {
        id: "node-policy",
        label: "Tata Kelola Core",
        sublabel: "Batas Keamanan",
        nodeType: "policy",
        status: "idle",
        badge: "Zero Host Tools",
        badgeVariant: "emerald",
        details: {
          policyText: "Tool host dinonaktifkan · Proteksi confinement aktif",
        },
      },
    },
    {
      id: "node-approval",
      type: "approval",
      position: { x: 1160, y: 160 },
      data: {
        id: "node-approval",
        label: "Persetujuan Core",
        sublabel: "Validasi Persyaratan",
        nodeType: "approval",
        status: isPublished
          ? "completed"
          : isApproved
            ? "completed"
            : isBenchPassed
              ? "waiting"
              : "blocked",
        badge: isPublished
          ? "Dipublikasikan"
          : isApproved
            ? "Disetujui"
            : isBenchPassed
              ? "Siap Persetujuan"
              : "Perlu Lulus Bench",
        badgeVariant: isPublished ? "emerald" : isBenchPassed ? "violet" : "amber",
        details: {
          hash: version?.payload_hash,
        },
      },
    },
    {
      id: "node-output",
      type: "arynOutput",
      position: { x: 1440, y: 160 },
      data: {
        id: "node-output",
        label: "Output Agen",
        sublabel: "Respons Riset Terstruktur",
        nodeType: "output",
        status: "idle",
        badge: "Teks / Markdown",
        badgeVariant: "default",
      },
    },
  ];

  const edges: Edge[] = [
    {
      id: "edge-input-agent",
      source: "node-input",
      target: "node-agent",
      type: "aryn",
      data: { status: "idle" },
    },
    {
      id: "edge-agent-model",
      source: "node-agent",
      target: "node-model",
      type: "aryn",
      data: { status: "idle" },
    },
    {
      id: "edge-model-knowledge",
      source: "node-model",
      target: "node-knowledge",
      type: "aryn",
      data: { status: "idle" },
    },
    {
      id: "edge-model-policy",
      source: "node-model",
      target: "node-policy",
      type: "aryn",
      data: { status: "idle" },
    },
    {
      id: "edge-knowledge-approval",
      source: "node-knowledge",
      target: "node-approval",
      type: "aryn",
      data: { status: "idle" },
    },
    {
      id: "edge-policy-approval",
      source: "node-policy",
      target: "node-approval",
      type: "aryn",
      data: { status: "idle" },
    },
    {
      id: "edge-approval-output",
      source: "node-approval",
      target: "node-output",
      type: "aryn",
      data: { status: isPublished ? "completed" : "idle" },
    },
  ];

  return { nodes, edges };
}

export function buildExecutionNodesAndEdges(
  run?: Run | null,
  version?: Version | null,
  isPending?: boolean,
): { nodes: Node[]; edges: Edge[] } {
  const isCompleted = run?.status === "completed";
  const isFailed = run?.status === "failed";

  const nodes: Node[] = [
    {
      id: "exec-input",
      type: "arynInput",
      position: { x: 50, y: 140 },
      data: {
        id: "exec-input",
        label: "Prompt Input",
        sublabel: "Permintaan Pengguna",
        nodeType: "input",
        status: isPending ? "completed" : run ? "completed" : "idle",
        badge: "Input Teks",
        badgeVariant: "default",
        details: {
          prompt: run?.prompt,
        },
      },
    },
    {
      id: "exec-agent",
      type: "agent",
      position: { x: 350, y: 140 },
      data: {
        id: "exec-agent",
        label: "Research Agent",
        sublabel: version ? `v${version.version_number} (Terkonfirmasi)` : "Agen Aktif",
        nodeType: "agent",
        status: isPending ? "running" : isCompleted ? "completed" : isFailed ? "failed" : "idle",
        badge: "Governed",
        badgeVariant: "emerald",
        details: {
          systemPrompt: version?.system_prompt,
        },
      },
    },
    {
      id: "exec-model",
      type: "model",
      position: { x: 650, y: 140 },
      data: {
        id: "exec-model",
        label: run?.model || version?.model || "Model Router",
        sublabel: run?.provider ? `Provider: ${run.provider}` : "Hermes Adapter",
        nodeType: "model",
        status: isPending ? "running" : isCompleted ? "completed" : isFailed ? "failed" : "idle",
        badge: isPending ? "Sedang Memproses…" : isCompleted ? "Selesai" : isFailed ? "Gagal" : "Siap",
        badgeVariant: isPending ? "cyan" : isCompleted ? "emerald" : isFailed ? "rose" : "default",
        metrics: run
          ? [
              { label: "Input Token", value: run.input_tokens || 0 },
              { label: "Output Token", value: run.output_tokens || 0 },
              { label: "Total Token", value: run.total_tokens || 0 },
            ]
          : undefined,
        details: {
          model: run?.model || version?.model,
        },
      },
    },
    {
      id: "exec-output",
      type: "arynOutput",
      position: { x: 950, y: 140 },
      data: {
        id: "exec-output",
        label: "Hasil Eksekusi",
        sublabel: "Teks Hasil Riset",
        nodeType: "output",
        status: isPending ? "queued" : isCompleted ? "completed" : isFailed ? "failed" : "idle",
        badge: isCompleted ? "Lengkap" : isFailed ? "Terputus" : isPending ? "Menunggu" : "Siap",
        badgeVariant: isCompleted ? "emerald" : isFailed ? "rose" : "default",
        details: {
          output: run?.output,
        },
      },
    },
  ];

  const edgeStatus = isPending ? "running" : isCompleted ? "completed" : isFailed ? "failed" : "idle";

  const edges: Edge[] = [
    {
      id: "exec-edge-1",
      source: "exec-input",
      target: "exec-agent",
      type: "aryn",
      data: { status: edgeStatus, animated: isPending },
    },
    {
      id: "exec-edge-2",
      source: "exec-agent",
      target: "exec-model",
      type: "aryn",
      data: { status: edgeStatus, animated: isPending },
    },
    {
      id: "exec-edge-3",
      source: "exec-model",
      target: "exec-output",
      type: "aryn",
      data: { status: edgeStatus, animated: isPending },
    },
  ];

  return { nodes, edges };
}

export function buildBenchNodesAndEdges(
  evaluation?: Evaluation | null,
  version?: Version | null,
  isPending?: boolean,
): { nodes: Node[]; edges: Edge[] } {
  const isVerifiedPass = Boolean(evaluation && evaluation.passed && evaluation.verified);
  const isUnverified = Boolean(evaluation && evaluation.passed && !evaluation.verified);
  const isFailed = Boolean(evaluation && !evaluation.passed);

  const scenarios = evaluation?.details || [
    { scenario_id: "prompt_injection", name: "Injeksi Prompt", category: "safety", passed: false },
    { scenario_id: "abstention_without_evidence", name: "Abstensi Tanpa Bukti", category: "truthfulness", passed: false },
    { scenario_id: "citation_faithfulness", name: "Ketepatan Sitasi", category: "faithfulness", passed: false },
    { scenario_id: "domain_restraint", name: "Batasan Ranah", category: "confinement", passed: false },
  ];

  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // Scenarios on the left
  scenarios.slice(0, 4).forEach((s, idx) => {
    const sId = `scenario-node-${idx}`;
    const sStatus = isPending ? "running" : evaluation ? (s.passed ? "completed" : "failed") : "idle";
    nodes.push({
      id: sId,
      type: "scenario",
      position: { x: 40, y: 40 + idx * 105 },
      data: {
        id: sId,
        label: scenarioNames[s.scenario_id] || s.name || `Skenario ${idx + 1}`,
        sublabel: s.category || "Evaluasi Keselamatan",
        nodeType: "scenario",
        status: sStatus,
        badge: s.passed ? "LULUS" : evaluation ? "GAGAL" : "STANDAR",
        badgeVariant: s.passed ? "emerald" : evaluation ? "rose" : "default",
        details: {
          category: s.category,
        },
      },
    });

    edges.push({
      id: `bench-edge-sc-${idx}`,
      source: sId,
      target: "bench-agent",
      type: "aryn",
      data: { status: sStatus, animated: isPending },
    });
  });

  // Agent Node
  nodes.push({
    id: "bench-agent",
    type: "agent",
    position: { x: 360, y: 195 },
    data: {
      id: "bench-agent",
      label: "Agen Subjek Uji",
      sublabel: version ? `v${version.version_number}` : "Versi Uji",
      nodeType: "agent",
      status: isPending ? "running" : evaluation ? "completed" : "idle",
      badge: "Target Bench",
      badgeVariant: "violet",
      details: {
        systemPrompt: version?.system_prompt,
      },
    },
  });

  // Hermes Runtime Adapter
  nodes.push({
    id: "bench-hermes",
    type: "hermes",
    position: { x: 640, y: 195 },
    data: {
      id: "bench-hermes",
      label: "Hermes Adapter",
      sublabel: "Turn Teks Terisolasi",
      nodeType: "hermes",
      status: isPending ? "running" : evaluation ? "completed" : "idle",
      badge: "Zero Tool Confinement",
      badgeVariant: "cyan",
    },
  });

  // Evaluation Result Node
  const evalStatus = isPending
    ? "running"
    : isVerifiedPass
      ? "completed"
      : isUnverified
        ? "blocked"
        : isFailed
          ? "failed"
          : "idle";

  nodes.push({
    id: "bench-evaluation",
    type: "evaluation",
    position: { x: 920, y: 195 },
    data: {
      id: "bench-evaluation",
      label: "Hasil Bench Core",
      sublabel: evaluation ? `${evaluation.passed_scenarios}/${evaluation.total_scenarios} Skenario` : "Belum Dievaluasi",
      nodeType: "evaluation",
      status: evalStatus,
      badge: isVerifiedPass
        ? "LULUS VERIFIED"
        : isUnverified
          ? "TIDAK TERVERIFIKASI"
          : isFailed
            ? "GAGAL"
            : "SIAGA",
      badgeVariant: isVerifiedPass ? "emerald" : isUnverified ? "amber" : isFailed ? "rose" : "default",
      metrics: evaluation
        ? [
            { label: "Skor", value: `${Math.round(evaluation.score * 100)}%` },
            { label: "Bukti", value: evaluation.verified ? "Valid" : "Invalid" },
          ]
        : undefined,
      details: {
        summary: isVerifiedPass
          ? "4/4 Lulus dengan Bukti Terverifikasi Core"
          : isUnverified
            ? "Hasil Historis · Bukti Tidak Valid untuk Governance"
            : isFailed
              ? "Satu atau Lebih Skenario Gagal"
              : "Siap Dievaluasi",
      },
    },
  });

  edges.push(
    {
      id: "bench-edge-agent-hermes",
      source: "bench-agent",
      target: "bench-hermes",
      type: "aryn",
      data: { status: isPending ? "running" : "idle", animated: isPending },
    },
    {
      id: "bench-edge-hermes-eval",
      source: "bench-hermes",
      target: "bench-evaluation",
      type: "aryn",
      data: { status: isPending ? "running" : evalStatus, animated: isPending },
    },
  );

  return { nodes, edges };
}
