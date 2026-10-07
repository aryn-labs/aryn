import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Beaker, Check, ChevronDown, ChevronRight, X } from "lucide-react";
import type { Evaluation, Shared } from "../lib/types";
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
                  {scenarioNames[s.scenario_id] || s.name || "Skenario evaluasi"}
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

  const selectedSuite = data.evaluation_suites?.find((suite) =>
    suite.suite_id === selectedVersion?.evaluation_reference?.suite_id ||
    suite.aliases.includes(selectedVersion?.evaluation_reference?.suite_id || "research-safety"));
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
            const idx = Number.isInteger(evt.data?.index) ? evt.data.index :
              scenarioDefinitions?.findIndex((s) => s.scenario_id === sId) ?? -1;
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
            const idx = Number.isInteger(evt.data?.index) ? evt.data.index :
              scenarioDefinitions?.findIndex((s) => s.scenario_id === sId) ?? -1;
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
          Bench' di atas untuk menjalankan suite evaluasi yang direferensikan versi
          agent.
        </Notice>
      )}
      {selectedEvaluation && !selectedEvaluation.verified && (
        <Notice tone="warning">
          Bukti evaluasi belum lolos validasi integritas dan konfigurasi saat ini.
          Evidence tidak dapat digunakan untuk pengajuan persetujuan Core.
        </Notice>
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
