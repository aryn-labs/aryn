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
  animated: boolean = false,
): Edge => ({
  id: `${source}-${target}`,
  source,
  target,
  type: "aryn",
  animated,
  data: { status, animated },
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
  const availability = version
    ? workspace?.models.find((m) => m.model_id === version.model)
        ?.availability || "unknown"
    : "unknown";

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
        : "Belum dikonfigurasi",
      nodeType: "agent",
      status: version
        ? version.integrity_valid
          ? "idle"
          : "blocked"
        : "waiting",
      badge: version
        ? published
          ? "Dipublikasikan"
          : approved
            ? "Disetujui"
            : "Konfigurasi tersimpan"
        : "Belum dikonfigurasi",
      badgeVariant:
        version && published && governanceValid ? "emerald" : "violet",
      details: { systemPrompt: version?.system_prompt },
    }),
    node("node-model", "model", 600, 160, {
      label: version?.model || "Model belum dipilih",
      sublabel: "Model Gateway",
      nodeType: "model",
      status: version
        ? availability === "unavailable"
          ? "failed"
          : availability === "unknown"
            ? "waiting"
            : "idle"
        : "waiting",
      badge: version ? availabilityLabel[availability] : "Belum dipilih",
      badgeVariant: version
        ? availability === "available"
          ? "emerald"
          : availability === "unknown"
            ? "amber"
            : "rose"
        : "amber",
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
      sublabel: version ? "Hash dan bukti Bench" : "Menunggu versi",
      nodeType: "approval",
      status: version
        ? (published || approved) && governanceValid
          ? "completed"
          : passing
            ? "waiting"
            : "blocked"
        : "waiting",
      badge: version
        ? published
          ? governanceValid
            ? "Sudah dipublikasikan"
            : "Dipublikasikan · bukti tidak berlaku"
          : approved
            ? governanceValid
              ? "Siap publikasi"
              : "Sudah disetujui · bukti tidak berlaku"
            : passing
              ? "Perlu persetujuan"
              : "Perlu Bench terverifikasi"
        : "Menunggu konfigurasi",
      badgeVariant:
        version && (published || approved) && governanceValid
          ? "emerald"
          : "amber",
      details: { hash: version?.payload_hash },
    }),
    node("node-output", "arynOutput", 1440, 160, {
      label: "Hasil agent",
      sublabel: version ? "Hasil tersedia sesudah eksekusi" : "Output kosong",
      nodeType: "output",
      status: "idle",
      badge: version ? "Respons teks" : "Output kosong",
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
  liveEvent?: { step: string; message?: string } | null,
) {
  const activeEvent = (!run || run.status === "running") ? liveEvent : null;
  const isInputActive =
    activeEvent?.step === "run.requested" || activeEvent?.step === "core.validating";
  const isDispatchActive = activeEvent?.step === "runtime.dispatching";
  const isPersistingActive = activeEvent?.step === "core.persisting";

  let runtimeStatus: NodeStatus = "idle";
  if (activeEvent) {
    if (activeEvent.step === "runtime.dispatching") runtimeStatus = "running";
    else if (
      activeEvent.step === "runtime.completed" ||
      activeEvent.step === "core.persisting" ||
      activeEvent.step === "run.completed"
    )
      runtimeStatus = "completed";
    else if (activeEvent.step === "run.failed") runtimeStatus = "failed";
  } else {
    runtimeStatus =
      run?.status === "completed"
        ? "completed"
        : run?.status === "failed"
          ? "failed"
          : ["running", "started"].includes(run?.status || "")
            ? "running"
            : run?.status === "queued"
              ? "queued"
              : "idle";
  }

  const outputStatus: NodeStatus = liveEvent
    ? liveEvent.step === "run.completed"
      ? "completed"
      : liveEvent.step === "run.failed"
        ? "failed"
        : isPersistingActive
          ? "running"
          : "idle"
    : run?.status === "failed"
      ? "failed"
      : run?.status === "completed"
        ? "completed"
        : "idle";

  const nodes = [
    node("exec-input", "arynInput", 40, 140, {
      label: "Instruksi run",
      sublabel: liveEvent
        ? "Instruksi diterima"
        : run
          ? "Masukan tersimpan"
          : "Belum ada run dipilih",
      nodeType: "input",
      status: isInputActive ? "running" : "idle",
      badge: isInputActive ? "Validasi Core…" : undefined,
      details: { prompt: run?.prompt },
    }),
    node("exec-agent", "agent", 330, 140, {
      label: agentName || "Konfigurasi historis agent",
      sublabel: version
        ? `Versi v${version.version_number}`
        : "Versi historis tidak tersedia",
      nodeType: "agent",
      status: isInputActive ? "running" : "idle",
      badge: isInputActive ? "Pemeriksaan tata kelola" : "Konfigurasi run ini",
      badgeVariant: "violet",
      details: { systemPrompt: version?.system_prompt },
    }),
    node("exec-model", "model", 620, 140, {
      label: run?.actual_model || run?.model || version?.model || "Model belum dilaporkan",
      sublabel: run?.gateway ? `Model Gateway` : "Gateway terverifikasi",
      nodeType: "model",
      status: isDispatchActive ? "running" : "idle",
      badge: isDispatchActive ? "Model dipanggil" : "Model tercatat",
      details: { model: run?.model || version?.model },
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
      badge: liveEvent
        ? isDispatchActive
          ? "Hermes mengeksekusi…"
          : runtimeStatus === "completed"
            ? "Runtime selesai"
            : "Memproses…"
        : run
          ? statusLabel(run.status)
          : "Belum ada run",
      badgeVariant:
        runtimeStatus === "failed"
          ? "rose"
          : runtimeStatus === "completed"
            ? "emerald"
            : runtimeStatus === "running"
              ? "cyan"
              : "default",
      details: { policyText: "Trace per-node tidak tersedia." },
    }),
    node("exec-output", "arynOutput", 1200, 140, {
      label: "Hasil eksekusi",
      sublabel: liveEvent
        ? isPersistingActive
          ? "Menyimpan output…"
          : outputStatus === "completed"
            ? "Respons tersimpan"
            : "Menunggu runtime"
        : "Respons tersimpan",
      nodeType: "output",
      status: outputStatus,
      badge:
        outputStatus === "completed"
          ? "Selesai"
          : outputStatus === "failed"
            ? "Gagal"
            : outputStatus === "running"
              ? "Persisting…"
              : undefined,
      badgeVariant:
        outputStatus === "completed"
          ? "emerald"
          : outputStatus === "failed"
            ? "rose"
            : "default",
      details: { output: run?.output },
    }),
  ];

  const edges = [
    edge(
      "exec-input",
      "exec-agent",
      isInputActive ? "running" : "idle",
      isInputActive,
    ),
    edge(
      "exec-agent",
      "exec-model",
      isDispatchActive ? "running" : "idle",
      isDispatchActive,
    ),
    edge(
      "exec-model",
      "exec-runtime",
      isDispatchActive ? "running" : "idle",
      isDispatchActive,
    ),
    edge(
      "exec-runtime",
      "exec-output",
      isPersistingActive ? "running" : "idle",
      isPersistingActive,
    ),
  ];

  return { nodes, edges };
}

export function buildBenchNodesAndEdges(
  evaluation?: Evaluation | null,
  version?: Version | null,
  liveBenchEvent?: {
    step: string;
    scenarioIndex?: number;
    scenarioId?: string;
    data?: any;
    scenarioStatuses?: Record<number, { passed?: boolean; status: NodeStatus }>;
  } | null,
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

  const standardSuite = Object.entries(scenarioNames).map(
    ([scenario_id, name]) => ({
      scenario_id,
      name,
      passed: undefined as boolean | undefined,
    }),
  );

  const scenarios = evaluation?.details || standardSuite;

  const activeIdx = liveBenchEvent?.scenarioIndex;
  const isScenarioActive = liveBenchEvent?.step === "scenario.started";

  const nodes = scenarios.map((s, i) => {
    let scenarioStatus: NodeStatus = "idle";
    let badge = "Skenario suite · belum dievaluasi";
    let badgeVariant: "default" | "violet" | "cyan" | "emerald" | "amber" | "rose" = "default";

    if (liveBenchEvent) {
      const recorded = liveBenchEvent.scenarioStatuses?.[i];
      if (recorded) {
        scenarioStatus = recorded.status;
        badge = recorded.passed ? "LULUS" : "GAGAL";
        badgeVariant = recorded.passed ? "emerald" : "rose";
      } else if (isScenarioActive && activeIdx === i) {
        scenarioStatus = "running";
        badge = "Sedang dievaluasi…";
        badgeVariant = "cyan";
      } else {
        scenarioStatus = "idle";
        badge = "Antrean suite";
      }
    } else if (evaluation) {
      scenarioStatus = !s.passed
        ? "failed"
        : !evaluation.verified
          ? "unverified"
          : "completed";
      badge = !s.passed
        ? "GAGAL"
        : evaluation.verified
          ? "LULUS"
          : "TIDAK TERVERIFIKASI";
      badgeVariant =
        scenarioStatus === "completed"
          ? "emerald"
          : scenarioStatus === "failed"
            ? "rose"
            : scenarioStatus === "unverified"
              ? "amber"
              : "default";
    }

    return node(`scenario-node-${i}`, "scenario", 40, 40 + i * 140, {
      label: scenarioNames[s.scenario_id] || s.name || s.scenario_id,
      nodeType: "scenario",
      status: scenarioStatus,
      badge,
      badgeVariant,
      details: { scenarioId: s.scenario_id },
    });
  });

  const agentStatus: NodeStatus = liveBenchEvent
    ? isScenarioActive
      ? "running"
      : "idle"
    : "idle";

  const hermesStatus: NodeStatus = liveBenchEvent
    ? isScenarioActive
      ? "running"
      : "idle"
    : "idle";

  const evalStatus: NodeStatus = liveBenchEvent
    ? liveBenchEvent.step === "bench.completed"
      ? liveBenchEvent.data?.passed
        ? "completed"
        : "failed"
      : "idle"
    : status;

  const evalBadge = liveBenchEvent
    ? liveBenchEvent.step === "bench.completed"
      ? liveBenchEvent.data?.passed
        ? "LULUS"
        : "GAGAL"
      : "Menunggu suite selesai"
    : state === "bench_passed"
      ? "LULUS"
      : state === "bench_unverified"
        ? "TIDAK TERVERIFIKASI"
        : state === "failed"
          ? "GAGAL"
          : "Belum ada hasil";

  nodes.push(
    node("bench-agent", "agent", 350, 220, {
      label: "Versi subjek evaluasi",
      sublabel: version
        ? `v${version.version_number}`
        : evaluation?.version_id || "Belum ada versi",
      nodeType: "agent",
      status: agentStatus,
      badge: liveBenchEvent && isScenarioActive ? "Memproses evaluasi…" : "Konfigurasi evaluasi",
      badgeVariant: "violet",
    }),
    node("bench-hermes", "hermes", 640, 220, {
      label: "Model yang dievaluasi",
      sublabel:
        evaluation?.provenance.requested_model ||
        version?.model ||
        "Belum dievaluasi",
      nodeType: "hermes",
      status: hermesStatus,
      badge:
        liveBenchEvent && isScenarioActive
          ? "Model merespons…"
          : evaluation
            ? "Respons historis tersimpan"
            : "Model Gateway siap",
      badgeVariant: liveBenchEvent && isScenarioActive ? "cyan" : "default",
    }),
    node("bench-evaluation", "evaluation", 930, 220, {
      label: "Hasil Bench Core",
      sublabel: evaluation
        ? `${evaluation.passed_scenarios}/${evaluation.total_scenarios} skenario`
        : liveBenchEvent?.data
          ? `${liveBenchEvent.data.passed_scenarios}/${liveBenchEvent.data.total_scenarios} skenario`
          : "Belum dievaluasi",
      nodeType: "evaluation",
      status: evalStatus,
      badge: evalBadge,
      badgeVariant:
        evalStatus === "completed"
          ? "emerald"
          : evalStatus === "failed"
            ? "rose"
            : evalStatus === "unverified"
              ? "amber"
              : "default",
      metrics: evaluation
        ? [{ label: "Skor", value: `${Math.round(evaluation.score * 100)}%` }]
        : liveBenchEvent?.data?.score !== undefined
          ? [{ label: "Skor", value: `${Math.round(liveBenchEvent.data.score * 100)}%` }]
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

  const edges = scenarios.map((_, i) => {
    const isThisScenarioActive = isScenarioActive && activeIdx === i;
    return edge(
      `scenario-node-${i}`,
      "bench-agent",
      isThisScenarioActive ? "running" : "idle",
      isThisScenarioActive,
    );
  });

  const isModelToHermesActive = Boolean(isScenarioActive);

  edges.push(
    edge(
      "bench-agent",
      "bench-hermes",
      isModelToHermesActive ? "running" : "idle",
      isModelToHermesActive,
    ),
    edge("bench-hermes", "bench-evaluation", evalStatus, false),
  );

  return { nodes, edges };
}
