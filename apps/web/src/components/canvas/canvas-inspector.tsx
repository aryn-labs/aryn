import { useId, useState } from "react";
import { Bot, Copy, Lock, Plus, ShieldCheck, X } from "lucide-react";
import { Button } from "../ui/button";
import { Notice, Status, scenarioNames, failureReason } from "../shared";
import { VersionForm } from "../version-form";
import { AuditList } from "../workspace";
import { date, number } from "../../lib/utils";
import { availabilityLabel, evaluationStatus } from "../../lib/studio-state";
import type { BaseNodeData, CanvasMode } from "./types";
import type {
  Assignment,
  Audit,
  Evaluation,
  Run,
  Version,
  Workspace,
} from "../../lib/types";

interface CanvasInspectorProps {
  mode: CanvasMode;
  selectedNode: BaseNodeData | null;
  onClose: () => void;
  version?: Version | null;
  workspace?: Workspace;
  versions?: Version[];
  pending?: boolean;
  error?: string;
  onCreateVersion?: (body: unknown) => Promise<void>;
  onRunBench?: () => void;
  onApproveVersion?: () => void;
  onPublishVersion?: () => void;
  run?: Run | null;
  assignment?: Assignment;
  auditEvents?: Audit[];
  evaluation?: Evaluation | null;
}

export function CanvasInspector({
  mode,
  selectedNode,
  onClose,
  version,
  workspace,
  versions = [],
  pending = false,
  error,
  onCreateVersion,
  onRunBench,
  onApproveVersion,
  onPublishVersion,
  run,
  assignment,
  auditEvents = [],
  evaluation,
}: CanvasInspectorProps) {
  const tabs =
    mode === "execution"
      ? [
          ["detail", "DETAIL"],
          ["output", "OUTPUT"],
          ["trace", "TRACE"],
        ]
      : mode === "bench"
        ? [
            ["skenario", "SKENARIO"],
            ["bukti", "BUKTI BENCH"],
          ]
        : [
            ["konfigurasi", "KONFIGURASI"],
            ["integritas", "TATA KELOLA"],
          ];
  const [activeTab, setActiveTab] = useState(tabs[0][0]);
  const [draft, setDraft] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState("");
  const id = useId();
  const availability =
    workspace?.models.find((m) => m.model_id === version?.model)
      ?.availability || "unknown";
  const benchState = evaluation
    ? evaluationStatus(evaluation)
    : "bench_unverified";
  const benchTone =
    benchState === "failed"
      ? "error"
      : benchState === "bench_passed"
        ? "success"
        : "warning";
  const scenarios =
    evaluation?.details.filter(
      (s) =>
        selectedNode?.nodeType !== "scenario" ||
        s.scenario_id === selectedNode.details?.scenarioId,
    ) || [];
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(run?.output || "");
      setCopied(true);
      setCopyError("");
    } catch {
      setCopyError(
        "Output belum dapat disalin. Pilih teks output untuk menyalinnya.",
      );
    }
  };
  return (
    <section className="canvas-inspector" aria-label="Inspector Node">
      <div className="inspector-header">
        <div className="inspector-title-group">
          <div className="inspector-node-type">
            {mode === "factory"
              ? draft
                ? "RANCANGAN LOKAL"
                : "VERSI TERSIMPAN · HANYA BACA"
              : "DATA TERSIMPAN · HANYA BACA"}
          </div>
          <h2 className="inspector-title">
            {draft ? "Rancang Versi Baru" : selectedNode?.label || "Pilih node"}
          </h2>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Tutup panel inspector"
          disabled={pending && draft}
          onClick={onClose}
        >
          <X size={16} />
        </Button>
      </div>
      {!selectedNode ? (
        <div className="inspector-empty-state">
          <Bot size={28} />
          <p>Pilih node menggunakan klik atau keyboard untuk memeriksa data.</p>
        </div>
      ) : (
        <>
          <div
            className="inspector-tabs"
            role="tablist"
            aria-label="Bagian inspector"
          >
            {tabs.map(([key, label], index) => (
              <button
                key={key}
                role="tab"
                id={`${id}-${key}`}
                aria-controls={`${id}-panel`}
                aria-selected={activeTab === key}
                tabIndex={activeTab === key ? 0 : -1}
                className={activeTab === key ? "active" : ""}
                onClick={() => setActiveTab(key)}
                onKeyDown={(e) => {
                  if (
                    ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)
                  ) {
                    e.preventDefault();
                    const next =
                      e.key === "Home"
                        ? 0
                        : e.key === "End"
                          ? tabs.length - 1
                          : (index +
                              (e.key === "ArrowRight" ? 1 : -1) +
                              tabs.length) %
                            tabs.length;
                    setActiveTab(tabs[next][0]);
                    document.getElementById(`${id}-${tabs[next][0]}`)?.focus();
                  }
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            className="inspector-content"
            role="tabpanel"
            id={`${id}-panel`}
            aria-labelledby={`${id}-${activeTab}`}
            tabIndex={0}
          >
            {mode === "execution" &&
              (run ? (
                <>
                  {activeTab === "detail" && (
                    <>
                      <Status value={run.status} />
                      <dl className="inspector-meta-list">
                        <dt>Core Run ID</dt>
                        <dd className="mono">{run.id}</dd>
                        <dt>Penugasan</dt>
                        <dd className="mono">
                          {assignment?.role_name ||
                            run.session_id ||
                            "Tidak tercatat"}
                        </dd>
                        <dt>Assignment ID</dt>
                        <dd className="mono">
                          {run.session_id || "Tidak tercatat"}
                        </dd>
                        <dt>Versi historis</dt>
                        <dd className="mono">
                          {version
                            ? `v${version.version_number} · ${version.id}`
                            : "Tidak tersedia"}
                        </dd>
                        <dt>Model tercatat</dt>
                        <dd className="mono">
                          {run.model || "Tidak dilaporkan"}
                        </dd>
                        <dt>Provider</dt>
                        <dd>{run.provider || "Tidak dilaporkan"}</dd>
                        <dt>Token input / output</dt>
                        <dd className="mono">
                          {number(run.input_tokens)} /{" "}
                          {number(run.output_tokens)}
                        </dd>
                        <dt>Total token</dt>
                        <dd className="mono">{number(run.total_tokens)}</dd>
                        <dt>Dibuat</dt>
                        <dd>{date(run.created_at)}</dd>
                        <dt>Selesai</dt>
                        <dd>{date(run.completed_at)}</dd>
                      </dl>
                      {version && (
                        <>
                          <div className="field-caption">
                            INSTRUKSI SISTEM VERSI HISTORIS
                          </div>
                          <pre tabIndex={0} className="inspector-code-block">
                            {version.system_prompt}
                          </pre>
                          <dl className="inspector-meta-list">
                            <dt>Temperature</dt>
                            <dd>{version.temperature}</dd>
                            <dt>Batas token</dt>
                            <dd>{version.max_tokens}</dd>
                          </dl>
                        </>
                      )}
                      <div className="field-caption">INSTRUKSI RUN</div>
                      <pre tabIndex={0} className="inspector-code-block">
                        {run.prompt}
                      </pre>
                    </>
                  )}
                  {activeTab === "output" && (
                    <>
                      {run.error_message && (
                        <Notice tone="error">{run.error_message}</Notice>
                      )}
                      <div className="field-caption">RESPONS TERSIMPAN</div>
                      <pre tabIndex={0} className="inspector-code-block">
                        {run.output || "Runtime belum memberikan output."}
                      </pre>
                      {run.output && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void copy()}
                        >
                          <Copy size={13} />
                          {copied ? "Tersalin" : "Salin output"}
                        </Button>
                      )}
                      {copyError && <Notice tone="warning">{copyError}</Notice>}
                    </>
                  )}
                  {activeTab === "trace" && (
                    <>
                      <Notice>
                        Trace runtime tidak tersedia. Jejak audit Core tersimpan
                        berikut adalah peristiwa aplikasi, bukan trace per-node
                        Hermes.
                      </Notice>
                      <AuditList events={auditEvents} />
                    </>
                  )}
                </>
              ) : (
                <Notice>
                  Belum ada run dipilih. Status eksekusi baru ditampilkan
                  terpisah sampai Core mengembalikan hasil.
                </Notice>
              ))}
            {mode === "factory" && version && (
              <>
                {activeTab === "konfigurasi" && (
                  <>
                    {draft && onCreateVersion ? (
                      <>
                        <Notice>
                          Rancangan ini belum tersimpan. Simpan membuat
                          AgentVersion baru; versi sumber tetap utuh.
                        </Notice>
                        {error && <Notice tone="error">{error}</Notice>}
                        <VersionForm
                          versions={versions}
                          models={workspace?.models || []}
                          previous={version}
                          pending={pending}
                          onSubmit={(body) => {
                            void onCreateVersion(body).catch(() => {});
                          }}
                        />
                        <Button
                          variant="ghost"
                          disabled={pending}
                          onClick={() => setDraft(false)}
                        >
                          Batalkan rancangan
                        </Button>
                      </>
                    ) : (
                      <>
                        <Notice>
                          <Lock size={14} /> Konfigurasi versi tersimpan hanya
                          baca.{" "}
                          {version.status === "published"
                            ? "Versi dipublikasikan tidak dapat diubah."
                            : "Perubahan disimpan melalui versi baru."}
                        </Notice>
                        <dl className="inspector-meta-list">
                          <dt>Versi</dt>
                          <dd className="mono">v{version.version_number}</dd>
                          <dt>Model</dt>
                          <dd className="mono">{version.model}</dd>
                          <dt>Temperature</dt>
                          <dd>{version.temperature}</dd>
                          <dt>Batas token</dt>
                          <dd>{version.max_tokens}</dd>
                        </dl>
                        <span
                          className={`provider-status-badge availability-${availability}`}
                        >
                          {availabilityLabel[availability]}
                        </span>
                        <div className="field-caption">
                          INSTRUKSI SISTEM · HANYA BACA
                        </div>
                        <pre tabIndex={0} className="inspector-code-block">
                          {version.system_prompt}
                        </pre>
                        {selectedNode.nodeType === "policy" && (
                          <Notice>
                            Core memeriksa izin, budget, dan confinement Hermes
                            sebelum dispatch. Status runtime saat ini:{" "}
                            {workspace?.runtime.message || "Belum diperiksa"}
                          </Notice>
                        )}
                        {onCreateVersion && (
                          <Button
                            className="w-full"
                            disabled={pending}
                            onClick={() => setDraft(true)}
                          >
                            <Plus size={15} />
                            Rancang Versi Baru
                          </Button>
                        )}
                        {selectedNode.nodeType === "approval" && (
                          <div className="approval-quick-actions">
                            {onRunBench && (
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={onRunBench}
                              >
                                Jalankan Bench
                              </Button>
                            )}
                            {onApproveVersion && (
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={onApproveVersion}
                              >
                                <ShieldCheck size={14} />
                                Tinjau dan setujui
                              </Button>
                            )}
                            {onPublishVersion && (
                              <Button size="sm" onClick={onPublishVersion}>
                                Publikasikan versi
                              </Button>
                            )}
                          </div>
                        )}
                      </>
                    )}
                  </>
                )}
                {activeTab === "integritas" && (
                  <>
                    <Status value={version.status} />
                    <div className="field-caption">
                      HASH KONFIGURASI SHA-256
                    </div>
                    <pre tabIndex={0} className="inspector-code-block">
                      {version.payload_hash}
                    </pre>
                    <dl className="inspector-meta-list">
                      <dt>Integritas versi</dt>
                      <dd>
                        {version.integrity_valid
                          ? "Valid menurut Core"
                          : "Tidak valid"}
                      </dd>
                      <dt>Evidence Bench eligible</dt>
                      <dd>
                        {version.bench_eligible
                          ? "Terverifikasi dan lulus"
                          : "Belum / tidak berlaku"}
                      </dd>
                      <dt>Governance</dt>
                      <dd>
                        {version.governance_valid
                          ? "Valid menurut Core"
                          : "Belum / tidak valid"}
                      </dd>
                      <dt>Dibuat</dt>
                      <dd>{date(version.created_at)}</dd>
                    </dl>
                  </>
                )}
              </>
            )}
            {mode === "bench" && evaluation && (
              <>
                <div className={`bench-score-banner text-${benchTone}`}>
                  <div className="score-percent">
                    {Math.round(evaluation.score * 100)}%
                  </div>
                  <div>
                    <Status value={benchState} />
                    <p>
                      {evaluation.passed_scenarios}/{evaluation.total_scenarios}{" "}
                      skenario tercatat lulus
                    </p>
                  </div>
                </div>
                {!evaluation.verified && (
                  <Notice tone="warning">
                    Hasil historis tetap disimpan. Evidence tidak terverifikasi
                    dan tidak dapat dipakai untuk approval/publish.
                  </Notice>
                )}
                {activeTab === "skenario" &&
                  scenarios.map((s) => (
                    <div
                      key={s.scenario_id}
                      className="scenario-inspector-item"
                    >
                      <strong>
                        {scenarioNames[s.scenario_id] ||
                          s.name ||
                          s.scenario_id}
                      </strong>
                      <Status
                        value={
                          !s.passed
                            ? "failed"
                            : !evaluation.verified
                              ? "bench_unverified"
                              : "bench_passed"
                        }
                      />
                      <p className="subtle">
                        {failureReason(s.failure_reason)}
                      </p>
                      <dl className="inspector-meta-list">
                        <dt>Model aktual tercatat</dt>
                        <dd>{s.actual_model || "Tidak dilaporkan"}</dd>
                        <dt>Token</dt>
                        <dd>{number(s.total_tokens)}</dd>
                        <dt>Latensi</dt>
                        <dd>{s.latency_seconds}s</dd>
                      </dl>
                      {selectedNode.nodeType === "scenario" && (
                        <pre tabIndex={0} className="inspector-code-block">
                          {s.actual_output || "Tidak ada respons tersimpan."}
                        </pre>
                      )}
                    </div>
                  ))}
                {activeTab === "bukti" && (
                  <dl className="inspector-meta-list">
                    <dt>Evaluation ID</dt>
                    <dd className="mono">{evaluation.id}</dd>
                    <dt>Version ID</dt>
                    <dd className="mono">{evaluation.version_id}</dd>
                    <dt>Model diminta</dt>
                    <dd>
                      {evaluation.provenance.requested_model ||
                        "Tidak tercatat"}
                    </dd>
                    <dt>Versi suite</dt>
                    <dd className="mono">
                      {evaluation.provenance.evaluation_version ||
                        "Tidak tercatat"}
                    </dd>
                    <dt>Hash konfigurasi</dt>
                    <dd className="mono">
                      {evaluation.provenance.payload_hash || "Tidak tercatat"}
                    </dd>
                    <dt>Dievaluasi</dt>
                    <dd>{date(evaluation.evaluated_at)}</dd>
                  </dl>
                )}
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}
