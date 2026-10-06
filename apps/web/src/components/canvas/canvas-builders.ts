import type { Node, Edge } from "@xyflow/react";
import type {
  Blueprint,
  Evaluation,
  Run,
  Version,
  Workspace,
} from "../../lib/types";
import { scenarioNames, statusLabel } from "../shared";
import { availabilityLabel, evaluationStatus } from "../../lib/studio-state";
import type { BaseNodeData, NodeStatus } from "./types";

const node = (
  id: string,
  type: string,
  x: number,
  y: number,
  data: Omit<BaseNodeData, "id">,
): Node => ({ id, type, position: { x, y }, data: { id, ...data } });
const edge = (
  source: string,
  target: string,
  status: NodeStatus = "idle",
): Edge => ({
  id: `${source}-${target}`,
  source,
  target,
  type: "aryn",
  data: { status },
});

export function buildFactoryNodesAndEdges(
  blueprint: Blueprint,
  version?: Version | null,
  workspace?: Workspace,
  project?: string,
) {
  const published = version?.status === "published";
  const approved = version?.status === "approved";
  const governanceValid =
    !!version?.integrity_valid && !!version?.governance_valid;
  const passing =
    version?.status === "draft" &&
    !!version.integrity_valid &&
    !!version.bench_eligible;
  const availability =
    workspace?.models.find((m) => m.model_id === version?.model)
      ?.availability || "unknown";
  const nodes = [
    node("node-input", "arynInput", 40, 160, {
      label: "Instruksi pengguna",
      sublabel: "Permintaan riset teks",
      nodeType: "input",
      status: "idle",
      badge: "Masukan teks",
    }),
    node("node-agent", "agent", 320, 160, {
      label: blueprint.name,
      sublabel: version
        ? `Versi v${version.version_number}`
        : "Belum ada versi",
      nodeType: "agent",
      status: version && !version.integrity_valid ? "blocked" : "idle",
      badge: published
        ? "Dipublikasikan"
        : approved
          ? "Disetujui"
          : "Konfigurasi tersimpan",
      badgeVariant: published && governanceValid ? "emerald" : "violet",
      details: { systemPrompt: version?.system_prompt },
    }),
    node("node-model", "model", 600, 160, {
      label: version?.model || "Model belum dipilih",
      sublabel: "Model Gateway · 9Router",
      nodeType: "model",
      status:
        availability === "unavailable"
          ? "failed"
          : availability === "unknown"
            ? "waiting"
            : "idle",
      badge: availabilityLabel[availability],
      badgeVariant:
        availability === "available"
          ? "emerald"
          : availability === "unknown"
            ? "amber"
            : "rose",
      metrics: version
        ? [
            { label: "Temperature", value: version.temperature },
            { label: "Batas token", value: version.max_tokens },
          ]
        : undefined,
      details: { model: version?.model, availability },
    }),
    node("node-knowledge", "knowledge", 880, 80, {
      label: "Konteks proyek",
      sublabel:
        workspace?.projects.find((p) => p.id === project)?.name ||
        "Lingkup blueprint",
      nodeType: "knowledge",
      status: "idle",
      badge: "Tanpa akses data eksternal",
      badgeVariant: "default",
    }),
    node("node-policy", "policy", 880, 240, {
      label: "Kebijakan Core",
      sublabel: "Gate sebelum eksekusi",
      nodeType: "policy",
      status: "idle",
      badge: "Riset teks tanpa tool",
      badgeVariant: "default",
      details: {
        policyText:
          "Core memeriksa confinement, izin, dan budget sebelum dispatch.",
      },
    }),
    node("node-approval", "approval", 1160, 160, {
      label: "Persetujuan manusia",
      sublabel: "Hash dan bukti Bench",
      nodeType: "approval",
      status:
        (published || approved) && governanceValid
          ? "completed"
          : passing
            ? "waiting"
            : "blocked",
      badge: published
        ? governanceValid
          ? "Sudah dipublikasikan"
          : "Dipublikasikan · bukti tidak berlaku"
        : approved
          ? governanceValid
            ? "Siap publikasi"
            : "Sudah disetujui · bukti tidak berlaku"
          : passing
            ? "Perlu persetujuan"
            : "Perlu Bench terverifikasi",
      badgeVariant:
        (published || approved) && governanceValid ? "emerald" : "amber",
      details: { hash: version?.payload_hash },
    }),
    node("node-output", "arynOutput", 1440, 160, {
      label: "Hasil agent",
      sublabel: "Hasil tersedia sesudah eksekusi",
      nodeType: "output",
      status: "idle",
      badge: "Respons teks",
    }),
  ];
  const edges = [
    edge("node-input", "node-agent"),
    edge("node-agent", "node-model"),
    edge("node-model", "node-knowledge"),
    edge("node-model", "node-policy"),
    edge("node-knowledge", "node-approval"),
    edge("node-policy", "node-approval"),
    edge("node-approval", "node-output"),
  ];
  return { nodes, edges };
}

export function buildExecutionNodesAndEdges(
  run?: Run | null,
  version?: Version | null,
  agentName?: string,
) {
  // Run status is aggregate evidence, never a per-node runtime trace.
  const runtimeStatus: NodeStatus =
    run?.status === "completed"
      ? "completed"
      : run?.status === "failed"
        ? "failed"
        : ["running", "started"].includes(run?.status || "")
          ? "running"
          : run?.status === "queued"
            ? "queued"
            : "idle";
  const nodes = [
    node("exec-input", "arynInput", 40, 140, {
      label: "Instruksi run",
      sublabel: run ? "Masukan tersimpan" : "Belum ada run dipilih",
      nodeType: "input",
      status: "idle",
      details: { prompt: run?.prompt },
    }),
    node("exec-agent", "agent", 330, 140, {
      label: agentName || "Konfigurasi historis agent",
      sublabel: version
        ? `Versi v${version.version_number}`
        : "Versi historis tidak tersedia",
      nodeType: "agent",
      status: "idle",
      badge: "Konfigurasi run ini",
      badgeVariant: "violet",
      details: { systemPrompt: version?.system_prompt },
    }),
    node("exec-model", "model", 620, 140, {
      label: run?.actual_model || run?.model || "Model belum dilaporkan",
      sublabel: run?.gateway
        ? `Model Gateway · ${run.gateway}`
        : "Gateway belum tercatat",
      nodeType: "model",
      status: "idle",
      badge: "Model tercatat",
      details: { model: run?.model },
      metrics: run
        ? [
            { label: "Token input", value: run.input_tokens },
            { label: "Token output", value: run.output_tokens },
            { label: "Total token", value: run.total_tokens },
          ]
        : undefined,
    }),
    node("exec-runtime", "hermes", 910, 140, {
      label: "Core / ARYN Runtime",
      sublabel: "Status keseluruhan run",
      nodeType: "hermes",
      status: runtimeStatus,
      badge: run ? statusLabel(run.status) : "Belum ada run",
      badgeVariant:
        runtimeStatus === "failed"
          ? "rose"
          : runtimeStatus === "completed"
            ? "emerald"
            : "default",
      details: { policyText: "Trace per-node tidak tersedia." },
    }),
    node("exec-output", "arynOutput", 1200, 140, {
      label: "Hasil eksekusi",
      sublabel: "Respons tersimpan",
      nodeType: "output",
      status:
        run?.status === "failed"
          ? "failed"
          : run?.status === "completed"
            ? "completed"
            : "idle",
      details: { output: run?.output },
    }),
  ];
  const edges = [
    edge("exec-input", "exec-agent"),
    edge("exec-agent", "exec-model"),
    edge("exec-model", "exec-runtime"),
    edge("exec-runtime", "exec-output"),
  ];
  return { nodes, edges };
}

export function buildBenchNodesAndEdges(
  evaluation?: Evaluation | null,
  version?: Version | null,
) {
  const state = evaluation ? evaluationStatus(evaluation) : undefined;
  const status: NodeStatus =
    state === "failed"
      ? "failed"
      : state === "bench_unverified"
        ? "unverified"
        : state === "bench_passed"
          ? "completed"
          : "idle";
  const scenarios =
    evaluation?.details ||
    Object.entries(scenarioNames).map(([scenario_id, name]) => ({
      scenario_id,
      name,
      passed: undefined,
    }));
  const nodes = scenarios.map((s, i) => {
    const scenarioStatus: NodeStatus = !evaluation
      ? "idle"
      : !s.passed
        ? "failed"
        : !evaluation.verified
          ? "unverified"
          : "completed";
    return node(`scenario-node-${i}`, "scenario", 40, 40 + i * 140, {
      label: scenarioNames[s.scenario_id] || s.name || s.scenario_id,
      nodeType: "scenario",
      status: scenarioStatus,
      badge: !evaluation
        ? "Skenario suite · belum dievaluasi"
        : !s.passed
          ? "GAGAL"
          : evaluation.verified
            ? "LULUS"
            : "TIDAK TERVERIFIKASI",
      badgeVariant:
        scenarioStatus === "completed"
          ? "emerald"
          : scenarioStatus === "failed"
            ? "rose"
            : scenarioStatus === "unverified"
              ? "amber"
              : "default",
      details: { scenarioId: s.scenario_id },
    });
  });
  nodes.push(
    node("bench-agent", "agent", 350, 220, {
      label: "Versi subjek evaluasi",
      sublabel: version
        ? `v${version.version_number}`
        : evaluation?.version_id || "Belum ada versi",
      nodeType: "agent",
      status: "idle",
      badge: "Konfigurasi evaluasi",
      badgeVariant: "violet",
    }),
    node("bench-hermes", "hermes", 640, 220, {
      label: "Model yang dievaluasi",
      sublabel: evaluation?.provenance.requested_model || "Belum dievaluasi",
      nodeType: "hermes",
      status: "idle",
      badge: "Respons historis tersimpan",
    }),
    node("bench-evaluation", "evaluation", 930, 220, {
      label: "Hasil Bench Core",
      sublabel: evaluation
        ? `${evaluation.passed_scenarios}/${evaluation.total_scenarios} skenario`
        : "Belum dievaluasi",
      nodeType: "evaluation",
      status,
      badge:
        state === "bench_passed"
          ? "LULUS"
          : state === "bench_unverified"
            ? "TIDAK TERVERIFIKASI"
            : state === "failed"
              ? "GAGAL"
              : "Belum ada hasil",
      badgeVariant:
        status === "completed"
          ? "emerald"
          : status === "failed"
            ? "rose"
            : status === "unverified"
              ? "amber"
              : "default",
      metrics: evaluation
        ? [{ label: "Skor", value: `${Math.round(evaluation.score * 100)}%` }]
        : undefined,
      details: {
        summary:
          state === "bench_passed"
            ? "Lulus dengan evidence terverifikasi"
            : state === "bench_unverified"
              ? "Histori tidak berlaku untuk approval/publish"
              : state === "failed"
                ? "Skenario atau skor gagal"
                : "Metadata suite; belum ada hasil",
      },
    }),
  );
  const edges = scenarios.map((_, i) =>
    edge(`scenario-node-${i}`, "bench-agent"),
  );
  edges.push(
    edge("bench-agent", "bench-hermes"),
    edge("bench-hermes", "bench-evaluation", status),
  );
  return { nodes, edges };
}
