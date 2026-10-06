import type { Node, Edge } from "@xyflow/react";
import type {
  Blueprint,
  Evaluation,
  Run,
  Version,
  Workspace,
} from "../../lib/types";
import { scenarioNames, statusLabel } from "../shared";
import { availabilityLabel } from "../../lib/studio-state";
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
  const standardScenarioKeys = [
    "scen_safety_injection_defense",
    "scen_tool_confinement_defense",
    "scen_research_accuracy_synthesis",
    "scen_grounded_abstention",
  ];

  const scenarios = standardScenarioKeys.map((key) => {
    const detail = evaluation?.details.find((d) => d.scenario_id === key);
    return {
      scenario_id: key,
      name: scenarioNames[key] || key,
      passed: detail?.passed,
      actual_output: detail?.actual_output || "",
      failure_reason: detail?.failure_reason || "",
      latency_seconds: detail?.latency_seconds || 0,
      total_tokens: detail?.total_tokens || 0,
      actual_model: detail?.actual_model || "",
    };
  });

  const activeIdx =
    typeof liveBenchEvent?.scenarioIndex === "number"
      ? liveBenchEvent.scenarioIndex
      : liveBenchEvent?.scenarioId
        ? standardScenarioKeys.indexOf(liveBenchEvent.scenarioId)
        : undefined;
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
      label: s.name,
      sublabel: s.actual_model || s.latency_seconds ? `${s.actual_model || "Model"} · ${s.latency_seconds}s` : undefined,
      nodeType: "scenario",
      status: scenarioStatus,
      badge,
      badgeVariant,
      details: {
        scenarioId: s.scenario_id,
        name: s.name,
        passed: s.passed,
        actual_output: s.actual_output,
        failure_reason: s.failure_reason,
        latency_seconds: s.latency_seconds,
        total_tokens: s.total_tokens,
        actual_model: s.actual_model,
      },
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

  let evalStatus: NodeStatus = "idle";
  let evalBadge = "Belum dievaluasi";
  let evalScore: string | undefined = undefined;
  let evalSublabel = "Belum dievaluasi";

  if (liveBenchEvent) {
    if (liveBenchEvent.step === "bench.completed") {
      const evalData = liveBenchEvent.data?.evaluation || liveBenchEvent.data;
      const passedCount = evalData?.passed_scenarios ?? Object.values(liveBenchEvent.scenarioStatuses || {}).filter(st => st.passed).length;
      const totalCount = evalData?.total_scenarios ?? 4;
      const isVerified = evalData?.verified ?? true;

      evalSublabel = `${passedCount}/${totalCount} skenario`;
      evalScore = evalData?.score !== undefined
        ? `${Math.round(evalData.score * 100)}%`
        : `${Math.round((passedCount / totalCount) * 100)}%`;

      if (passedCount === totalCount && isVerified) {
        evalStatus = "completed";
        evalBadge = "LULUS";
      } else if (passedCount === totalCount && !isVerified) {
        evalStatus = "unverified";
        evalBadge = "TIDAK TERVERIFIKASI";
      } else {
        evalStatus = "failed";
        evalBadge = "GAGAL";
      }
    } else {
      evalStatus = "running";
      evalBadge = "Sedang mengevaluasi…";
      evalSublabel = "Bench berlangsung";
    }
  } else if (evaluation) {
    evalSublabel = `${evaluation.passed_scenarios}/${evaluation.total_scenarios} skenario`;
    evalScore = `${Math.round(evaluation.score * 100)}%`;
    if (evaluation.passed_scenarios === 4 && evaluation.verified) {
      evalStatus = "completed";
      evalBadge = "LULUS";
    } else if (evaluation.passed_scenarios === 4 && !evaluation.verified) {
      evalStatus = "unverified";
      evalBadge = "TIDAK TERVERIFIKASI";
    } else {
      evalStatus = "failed";
      evalBadge = "GAGAL";
    }
  }

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
      sublabel: evalSublabel,
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
      metrics: evalScore ? [{ label: "Skor", value: evalScore }] : undefined,
      details: {
        summary:
          evalStatus === "completed"
            ? "Lulus dengan evidence terverifikasi"
            : evalStatus === "unverified"
              ? "Histori tidak berlaku untuk approval/publish"
              : evalStatus === "failed"
                ? "Skenario atau skor gagal"
                : "Metadata suite; belum ada hasil",
      },
    }),
  );

  const edges = scenarios.map((_, i) => {
    const isThisScenarioActive = Boolean(isScenarioActive && activeIdx === i);
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
    edge("bench-hermes", "bench-evaluation", evalStatus === "running" ? "running" : "idle", false),
  );

  return { nodes, edges };
}
