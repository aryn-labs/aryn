import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Beaker, Check, ChevronDown, ChevronRight, X } from "lucide-react";
import type { Evaluation, RegressionComparison, Shared } from "../lib/types";
import { readBenchCompletion } from "../lib/api";
import { date, number } from "../lib/utils";
import { Button } from "../components/ui/button";
import {
  Empty,
  Notice,
  PageHeading,
  Status,
  scenarioNames,
  failureReason,
} from "../components/shared";
import { Panel } from "../components/workspace";
import { ArynCanvas } from "../components/canvas/aryn-canvas";
import { buildBenchNodesAndEdges } from "../components/canvas/canvas-builders";
import type { NodeStatus } from "../components/canvas/types";
import { evaluationStatus, executionReady } from "../lib/studio-state";
export { evaluationStatus } from "../lib/studio-state";

export function RegressionPanel({
  comparison,
}: {
  comparison: RegressionComparison;
}) {
  const signed = (value: number | null | undefined) =>
    value == null
      ? "Tidak tersedia"
      : `${value > 0 ? "+" : ""}${number(value)}`;
  return (
    <Panel
      id="regression-comparison"
      title="Accepted Baseline vs Candidate"
      subtitle={`${comparison.suite_id} · ${comparison.evaluation_version}`}
    >
      <Notice tone={comparison.promotion_blocked ? "error" : "success"}>
        {comparison.promotion_blocked
          ? "Promotion diblokir"
          : "Eligible untuk tinjauan promotion"}
        {` · ${comparison.critical_regressions.length} regression kritis · ${comparison.state}`}
      </Notice>
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label="Identitas baseline dan candidate"
      >
        <table>
          <thead>
            <tr>
              <th>Accepted Baseline</th>
              <th>Candidate</th>
              <th>Delta skor</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                {comparison.baseline
                  ? `v${comparison.baseline.version_number}`
                  : comparison.state === "bootstrap"
                    ? "Bootstrap publication pertama"
                    : "Baseline diperlukan"}
                <small className="table-sub mono">
                  {comparison.baseline?.evaluation_id || comparison.reason}
                </small>
              </td>
              <td>
                v{comparison.candidate.version_number}
                <small className="table-sub mono">
                  {comparison.candidate.evaluation_id}
                </small>
              </td>
              <td>{signed(comparison.score_delta)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        className="table-scroll"
        tabIndex={0}
        role="region"
        aria-label="Delta metric baseline dan candidate"
      >
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th>Baseline</th>
              <th>Candidate</th>
              <th>Delta</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(comparison.metrics).map(([name, metric]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{metric.baseline ?? "Tidak tersedia"}</td>
                <td>{metric.candidate ?? "Tidak tersedia"}</td>
                <td>
                  {metric.state === "comparable"
                    ? signed(metric.delta)
                    : metric.state}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {comparison.scenarios
        .filter((s) => s.regression || s.graders.some((g) => g.regression))
        .map((s) => (
          <details key={s.scenario_id} className="scenario-result" open>
            <summary>
              <strong>{s.scenario_id}</strong>
              <span>
                {s.baseline_state} → {s.candidate_state}
                {s.critical ? " · kritis" : ""}
              </span>
            </summary>
            <ul>
              {s.graders
                .filter((g) => g.regression)
                .map((g) => (
                  <li key={g.grader_id}>
                    {g.grader_id} ({g.grader_type}): {g.baseline_state} →{" "}
                    {g.candidate_state}
                    {g.critical ? " · kritis" : ""} · {g.candidate_reason}
                  </li>
                ))}
            </ul>
          </details>
        ))}
      {comparison.regressions
        .filter(
          (r) =>
            r.kind === "comparability" ||
            r.kind === "evidence" ||
            (r.kind === "metric" && r.critical),
        )
        .map((r, index) => (
          <Notice key={index} tone="error">
            {r.reason}
            {typeof r.details.metric === "string"
              ? ` · ${r.details.metric}`
              : ""}
          </Notice>
        ))}
      {comparison.limitations.length > 0 && (
        <Notice tone="warning">{comparison.limitations.join(" · ")}</Notice>
      )}
      <div className="panel-footnote mono">
        {comparison.comparison_id} · {date(comparison.compared_at)}
      </div>
    </Panel>
  );
}

export function EvaluationPanel({
  evaluation,
  showCanvas = true,
}: {
  evaluation: Evaluation;
  showCanvas?: boolean;
}) {
  const status = evaluationStatus(evaluation);
  const unverified = status === "bench_unverified";
  const passed = status === "bench_passed";

  const { nodes: benchNodes, edges: benchEdges } = useMemo(() => {
    return buildBenchNodesAndEdges(evaluation);
  }, [evaluation]);

  return (
    <Panel
      id="evaluasi-bench"
      title={
        unverified
          ? "Evaluasi tidak terverifikasi"
          : passed
            ? "Evaluasi lulus"
            : "Evaluasi belum lulus"
      }
      subtitle={`${date(evaluation.evaluated_at)} · ${evaluation.provenance.evaluation_version || "Provenance belum tersedia"}`}
      action={
        <div className="flex items-center gap-3">
          <Status value={status} />
          <span
            className={`score ${unverified ? "text-warning" : passed ? "text-success" : "text-error"}`}
          >
            {Math.round(evaluation.score * 100)}%
            <small>
              {evaluation.passed_scenarios}/{evaluation.total_scenarios}{" "}
              skenario
            </small>
          </span>
        </div>
      }
    >
      {showCanvas && (
        <div className="bench-canvas-section mb-4">
          <ArynCanvas
            mode="bench"
            initialNodes={benchNodes}
            initialEdges={benchEdges}
            evaluation={evaluation}
            showInspectorByDefault={false}
          />
        </div>
      )}
      <div className="evaluation-notice">
        <Notice tone={unverified ? "warning" : passed ? "success" : "error"}>
          {unverified
            ? "Hasil historis tetap disimpan, tetapi bukti/provenance sudah tidak valid atau berasal dari format lama. Hasil ini tidak dapat digunakan untuk persetujuan atau publikasi. Jalankan Bench pada versi yang valid untuk memperoleh bukti terverifikasi."
            : passed
              ? "Seluruh skenario memenuhi kriteria. Versi dapat ditinjau untuk persetujuan."
              : "Publikasi diblokir. Tinjau respons dan alasan setiap kegagalan, lalu buat versi yang diperbaiki."}
        </Notice>
      </div>
      <div className="scenario-results">
        {evaluation.details.map((s) => (
          <details key={s.scenario_id} className="scenario-result">
            <summary>
              <div
                className={
                  !s.passed
                    ? "scenario-check error"
                    : unverified
                      ? "scenario-check warning"
                      : "scenario-check success"
                }
              >
                {s.passed ? <Check size={15} /> : <X size={15} />}
              </div>
              <div>
                <strong>
                  {scenarioNames[s.scenario_id] ||
                    s.name ||
                    "Skenario evaluasi"}
                </strong>
                <small>{failureReason(s.failure_reason)}</small>
              </div>
              <span className="mono subtle">{s.latency_seconds}s</span>
              <Status
                value={
                  !s.passed
                    ? "failed"
                    : unverified
                      ? "bench_unverified"
                      : "bench_passed"
                }
              />
              <ChevronDown size={15} />
            </summary>
            <div className="scenario-output">
              <div className="output-meta">
                <span>
                  {evaluation.verified
                    ? "RESPONS MODEL AKTUAL"
                    : "RESPONS HISTORIS TERSIMPAN"}
                </span>
                <code>{s.actual_model || "Model belum dilaporkan"}</code>
                <span>{number(s.total_tokens || 0)} token</span>
              </div>
              <pre className="prompt-output">
                {s.actual_output || "Tidak ada respons dari runtime."}
              </pre>
            </div>
          </details>
        ))}
      </div>
      <div className="panel-footnote mono">
        {evaluation.id} · Model diminta:{" "}
        {evaluation.provenance.requested_model || "Tidak tercatat"}
      </div>
    </Panel>
  );
}

export function BenchPage({
  data,
  workspace,
  pending = false,
  act,
  actStream,
}: Partial<Shared> & Pick<Shared, "data">) {
  const [params, setParams] = useSearchParams();
  const [benchRunning, setBenchRunning] = useState(false);
  const [benchError, setBenchError] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [baselineReason, setBaselineReason] = useState("");
  const [suiteTransition, setSuiteTransition] = useState(false);
  const [completedEvaluation, setCompletedEvaluation] =
    useState<Evaluation | null>(null);

  // Active version ID from params or first available version
  const activeVersionId = useMemo(() => {
    const fromParam = params.get("versi");
    if (fromParam && data.versions.some((v) => v.id === fromParam))
      return fromParam;
    const evalId = params.get("evaluasi");
    if (evalId) {
      const match = data.evaluations.find((e) => e.id === evalId);
      if (match) return match.version_id;
    }
    return data.versions[0]?.id || "";
  }, [params, data.versions, data.evaluations]);

  const selectedVersion = useMemo(() => {
    return data.versions.find((v) => v.id === activeVersionId) || null;
  }, [data.versions, activeVersionId]);
  useEffect(() => {
    setBaselineReason("");
    setSuiteTransition(false);
  }, [activeVersionId]);

  // STRICT SYNC: Only evaluations for the active version!
  const versionEvaluations = useMemo(() => {
    return data.evaluations.filter((e) => e.version_id === activeVersionId);
  }, [data.evaluations, activeVersionId]);

  const selectedEvaluation = useMemo(() => {
    const evalId = params.get("evaluasi");
    if (evalId) {
      return (
        versionEvaluations.find((e) => e.id === evalId) ||
        (completedEvaluation?.id === evalId &&
        completedEvaluation.version_id === activeVersionId
          ? completedEvaluation
          : null)
      );
    }
    // Default to the first evaluation OF THIS VERSION ONLY (never another version)
    return versionEvaluations[0] || null;
  }, [versionEvaluations, params, completedEvaluation, activeVersionId]);

  const [liveBenchEvent, setLiveBenchEvent] = useState<{
    step: string;
    scenarioIndex?: number;
    scenarioId?: string;
    data?: any;
    scenarioStatuses?: Record<number, { passed?: boolean; status: NodeStatus }>;
    scenarios?: import("../lib/types").ScenarioDefinition[];
  } | null>(null);

  const selectedSuite = data.evaluation_suites?.find(
    (suite) =>
      suite.suite_id === selectedVersion?.evaluation_reference?.suite_id ||
      suite.aliases.includes(
        selectedVersion?.evaluation_reference?.suite_id || "research-safety",
      ),
  );
  const { nodes: benchNodes, edges: benchEdges } = useMemo(() => {
    return buildBenchNodesAndEdges(
      selectedEvaluation,
      selectedVersion,
      liveBenchEvent,
      selectedSuite,
    );
  }, [selectedEvaluation, selectedVersion, liveBenchEvent, selectedSuite]);

  const runBench = async () => {
    if (!activeVersionId || !act) return;
    setBenchError(null);
    setBenchRunning(true);
    const selectCompletion = (value: unknown) => {
      const result = readBenchCompletion(value);
      if (result.version_id !== activeVersionId) {
        throw new Error("Hasil Bench tidak sesuai versi yang dievaluasi.");
      }
      setCompletedEvaluation(result.evaluation);
      setParams({ versi: result.version_id, evaluasi: result.evaluation_id });
    };
    const scenarioStatuses: Record<
      number,
      { passed?: boolean; status: NodeStatus }
    > = {};
    let scenarioDefinitions = selectedSuite?.scenarios;
    setLiveBenchEvent({
      step: "bench.started",
      scenarioStatuses: {},
    });

    try {
      const runner = actStream || act;
      const res = await runner(
        `/versions/${activeVersionId}/bench`,
        { allow_remote_model: consent },
        "Bench selesai dievaluasi.",
        (evt: any) => {
          if (!evt) return;
          if (evt.type === "bench.started") {
            scenarioDefinitions = evt.data?.scenarios;
            setLiveBenchEvent({
              step: "bench.started",
              scenarios: evt.data?.scenarios,
              scenarioStatuses: { ...scenarioStatuses },
            });
          } else if (evt.type === "scenario.started") {
            const sId = evt.data?.scenario_id;
            const idx = Number.isInteger(evt.data?.index)
              ? evt.data.index
              : (scenarioDefinitions?.findIndex((s) => s.scenario_id === sId) ??
                -1);
            if (idx >= 0) {
              setLiveBenchEvent({
                step: "scenario.started",
                scenarios: scenarioDefinitions,
                scenarioId: sId,
                scenarioIndex: idx,
                scenarioStatuses: { ...scenarioStatuses },
              });
            }
          } else if (evt.type === "scenario.completed") {
            const sId = evt.data?.scenario_id;
            const idx = Number.isInteger(evt.data?.index)
              ? evt.data.index
              : (scenarioDefinitions?.findIndex((s) => s.scenario_id === sId) ??
                -1);
            if (idx >= 0) {
              scenarioStatuses[idx] = {
                passed: evt.data?.passed,
                status: evt.data?.passed ? "completed" : "failed",
              };
              setLiveBenchEvent({
                step: "scenario.completed",
                scenarios: scenarioDefinitions,
                scenarioId: sId,
                scenarioIndex: idx,
                scenarioStatuses: { ...scenarioStatuses },
                data: evt.data,
              });
            }
          } else if (evt.type === "bench.completed") {
            selectCompletion(evt.data);
            setLiveBenchEvent({
              step: "bench.completed",
              scenarioStatuses: { ...scenarioStatuses },
              data: evt.data?.evaluation || evt.data,
            });
          }
        },
      );
      selectCompletion(res);
    } catch (err: any) {
      setBenchError(err.message || "Gagal menjalankan evaluasi Bench");
    } finally {
      setBenchRunning(false);
      setLiveBenchEvent(null);
    }
  };

  const isReady = workspace ? executionReady(workspace) : true;
  const canRun =
    !benchRunning &&
    !pending &&
    Boolean(activeVersionId) &&
    consent &&
    isReady &&
    (data.permissions ? Boolean(data.permissions["run:create"]) : true);

  return (
    <>
      <PageHeading
        eyebrow="EVALUASI"
        title="Bench"
        description="Bukti keselamatan dan kualitas, sebelum sebuah versi dipublikasikan."
      />

      <div className="detail-toolbar mb-4">
        <div className="version-picker">
          <label htmlFor="bench-version-select" className="sr-only">
            Pilih versi untuk dievaluasi
          </label>
          <select
            id="bench-version-select"
            aria-label="Pilih versi untuk dievaluasi"
            value={activeVersionId}
            onChange={(e) => {
              // Clearing evaluasi ensures switching versions never displays another version's evaluation
              setParams({ versi: e.target.value });
              setLiveBenchEvent(null);
            }}
            disabled={benchRunning || pending}
          >
            {data.versions.length ? (
              data.versions.map((v) => {
                const bp = data.blueprints.find((b) => b.id === v.blueprint_id);
                return (
                  <option key={v.id} value={v.id}>
                    {bp ? `${bp.name} · ` : ""}v{v.version_number} ({v.model})
                  </option>
                );
              })
            ) : (
              <option value="">Belum ada versi agent</option>
            )}
          </select>
        </div>
        <div className="flex items-center gap-3">
          <label className="checkbox-field text-sm">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              disabled={benchRunning || pending}
            />
            Persetujuan model
          </label>
          <Button onClick={runBench} disabled={!canRun} variant="default">
            <Beaker size={15} />
            {benchRunning ? "Mengevaluasi…" : "Jalankan Bench"}
          </Button>
        </div>
      </div>

      {benchError && <Notice tone="error">{benchError}</Notice>}
      {benchRunning && (
        <Notice tone="info">
          Uji kepatuhan Bench sedang berlangsung… Memvalidasi skenario suite
          yang direferensikan versi agent.
        </Notice>
      )}
      {!selectedEvaluation && selectedVersion && !benchRunning && (
        <Notice tone="info">
          Versi ini belum pernah dievaluasi di Bench Laboratory. Klik 'Jalankan
          Bench' di atas untuk menjalankan suite evaluasi yang direferensikan
          versi agent.
        </Notice>
      )}
      {selectedEvaluation && !selectedEvaluation.verified && (
        <Notice tone="warning">
          Bukti evaluasi belum lolos validasi integritas dan konfigurasi saat
          ini. Evidence tidak dapat digunakan untuk pengajuan persetujuan Core.
        </Notice>
      )}

      {selectedVersion?.regression && (
        <RegressionPanel comparison={selectedVersion.regression} />
      )}
      {selectedEvaluation?.verified &&
        selectedEvaluation.passed === 1 &&
        data.permissions?.["bench:accept_baseline"] &&
        act &&
        selectedVersion?.evaluation_id === selectedEvaluation.id &&
        selectedVersion.regression?.baseline?.evaluation_id !==
          selectedEvaluation.id && (
          <Panel
            title="Penerimaan baseline"
            subtitle="Keputusan admin dicatat oleh Core; baseline sebelumnya tetap menjadi riwayat."
          >
            <label className="checkbox-field text-sm">
              Alasan governance
              <input
                aria-label="Alasan penerimaan baseline"
                value={baselineReason}
                onChange={(e) => setBaselineReason(e.target.value)}
                maxLength={2000}
              />
            </label>
            {selectedVersion.regression?.state === "incompatible" && (
              <label className="checkbox-field text-sm">
                <input
                  type="checkbox"
                  checked={suiteTransition}
                  onChange={(e) => setSuiteTransition(e.target.checked)}
                />
                Terima transisi suite/evidence secara eksplisit
              </label>
            )}
            <Button
              disabled={
                pending ||
                baselineReason.trim().length < 3 ||
                Boolean(
                  selectedVersion.regression?.promotion_blocked &&
                  !(
                    selectedVersion.regression.state === "incompatible" &&
                    suiteTransition
                  ) &&
                  !(
                    selectedVersion.regression.state === "baseline_required" &&
                    ["published", "deprecated"].includes(selectedVersion.status)
                  ),
                )
              }
              onClick={() =>
                act(
                  `/blueprints/${selectedVersion.blueprint_id}/baseline`,
                  {
                    evaluation_id: selectedEvaluation.id,
                    expected_baseline_id:
                      selectedVersion.regression?.baseline_id || null,
                    reason: baselineReason,
                    suite_transition: suiteTransition,
                  },
                  "Baseline diterima.",
                )
              }
            >
              Terima sebagai baseline
            </Button>
          </Panel>
        )}

      {/* Primary Workspace: Bench Canvas & Inspector */}
      <div className="bench-canvas-workspace mb-6">
        <ArynCanvas
          mode="bench"
          initialNodes={benchNodes}
          initialEdges={benchEdges}
          evaluation={selectedEvaluation}
          version={selectedVersion}
          showInspectorByDefault={Boolean(selectedEvaluation)}
          pending={benchRunning || pending}
          onRunBench={canRun ? runBench : undefined}
        />
      </div>

      <Panel
        className="mt-6"
        title="Riwayat evaluasi"
        subtitle={`${data.evaluations.length} hasil evaluasi tersimpan di database proyek.`}
      >
        {data.evaluations.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Agent / versi</th>
                  <th>Hasil</th>
                  <th>Skor</th>
                  <th>Skenario</th>
                  <th>Dievaluasi</th>
                  <th>
                    <span className="sr-only">Aksi</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.evaluations.map((e) => {
                  const v = data.versions.find((v) => v.id === e.version_id);
                  const isCurrent = selectedEvaluation?.id === e.id;
                  return (
                    <tr
                      key={e.id}
                      className={isCurrent ? "table-row-selected" : ""}
                    >
                      <td>
                        <strong>
                          {data.blueprints.find((b) => b.id === e.blueprint_id)
                            ?.name || e.blueprint_id}
                        </strong>
                        <small className="table-sub mono">
                          v{v?.version_number}
                        </small>
                      </td>
                      <td>
                        <Status value={evaluationStatus(e)} />
                      </td>
                      <td className="mono">{Math.round(e.score * 100)}%</td>
                      <td>
                        {e.passed_scenarios}/{e.total_scenarios}
                      </td>
                      <td className="subtle">{date(e.evaluated_at)}</td>
                      <td>
                        <Button
                          variant={isCurrent ? "secondary" : "ghost"}
                          size="sm"
                          onClick={() => {
                            setParams({ versi: e.version_id, evaluasi: e.id });
                          }}
                          aria-label={`Lihat hasil evaluasi ${e.id}`}
                        >
                          Lihat hasil
                          <ChevronRight size={14} />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Belum ada evaluasi Bench"
            description="Pilih versi pada bilah alat di atas, lalu klik 'Jalankan Bench' untuk menjalankan suite evaluasi versi tersebut."
          />
        )}
      </Panel>
    </>
  );
}
