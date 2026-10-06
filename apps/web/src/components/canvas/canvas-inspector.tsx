import { useId, useState } from "react";
import {
  Bot,
  Check,
  Copy,
  Lock,
  Maximize2,
  Plus,
  ShieldCheck,
  Workflow,
  X,
  Beaker,
  ArrowDownToLine,
} from "lucide-react";
import { Button } from "../ui/button";
import { Modal } from "../ui/dialog";
import { Notice, Status, scenarioNames, failureReason } from "../shared";
import { VersionForm } from "../version-form";
import { AuditList } from "../workspace";
import { date, number } from "../../lib/utils";
import {
  availabilityLabel,
  evaluationStatus,
  executionReady,
  gatewayStatus,
} from "../../lib/studio-state";
import type { BaseNodeData, CanvasMode } from "./types";
import type {
  Assignment,
  Audit,
  Blueprint,
  Evaluation,
  Run,
  Version,
  Workspace,
} from "../../lib/types";

interface InspectorTextBlockProps {
  label: string;
  content?: string | null;
  emptyText?: string;
  subtitle?: string;
}

export function InspectorTextBlock({
  label,
  content,
  emptyText = "Tidak ada teks tersimpan.",
  subtitle,
}: InspectorTextBlockProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const textToCopy = content || "";

  const handleCopy = async () => {
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard write errors
    }
  };

  const hasContent = Boolean(content && content.trim().length > 0);

  return (
    <div className="inspector-text-block-wrapper">
      <div className="inspector-text-header">
        <div className="field-caption">{label}</div>
        {hasContent && (
          <div className="inspector-text-actions">
            <button
              type="button"
              className="inspector-action-btn"
              onClick={() => void handleCopy()}
              title={copied ? "Tersalin ke clipboard" : "Salin teks"}
              aria-label={`Salin ${label}`}
            >
              {copied ? (
                <Check size={11} className="text-success" />
              ) : (
                <Copy size={11} />
              )}
              <span>{copied ? "Tersalin" : "Salin"}</span>
            </button>
            <button
              type="button"
              className="inspector-action-btn action-expand"
              onClick={() => setModalOpen(true)}
              title="Baca selengkapnya di jendela popup"
              aria-label={`Baca selengkapnya ${label}`}
            >
              <Maximize2 size={11} />
              <span>Baca selengkapnya</span>
            </button>
          </div>
        )}
      </div>

      <pre tabIndex={0} className="inspector-code-block">
        {content || emptyText}
      </pre>

      {hasContent && (
        <Modal
          open={modalOpen}
          onOpenChange={setModalOpen}
          title={label}
          description={subtitle || "Tampilan teks lengkap dan terformat."}
        >
          <div className="inspector-modal-body">
            <div className="inspector-modal-toolbar">
              <span className="subtle text-xs mono">
                {content ? `${content.length} karakter` : ""}
              </span>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void handleCopy()}
              >
                {copied ? (
                  <Check size={13} className="text-success" />
                ) : (
                  <Copy size={13} />
                )}
                {copied ? "Tersalin ke clipboard" : "Salin semua teks"}
              </Button>
            </div>
            <pre tabIndex={0} className="inspector-modal-pre">
              {content}
            </pre>
          </div>
        </Modal>
      )}
    </div>
  );
}

export interface PublishedAgentItem {
  versionId: string;
  blueprintId: string;
  blueprintName: string;
  versionNumber: string;
  model: string;
  assignmentId?: string;
  roleName?: string;
  isAssigned: boolean;
  integrityValid?: boolean;
  governanceValid?: boolean;
}

export interface ExecutionFormConfig {
  publishedAgents: PublishedAgentItem[];
  selectedVersionId: string;
  onSelectVersion: (versionId: string) => void;
  // Inline assignment creation
  roleInput: string;
  onRoleInputChange: (role: string) => void;
  onCreateAssignment: () => Promise<void>;
  creatingAssignment: boolean;
  // Execution inputs
  prompt: string;
  onPromptChange: (p: string) => void;
  consent: boolean;
  onConsentChange: (c: boolean) => void;
  onSubmit: (e?: React.FormEvent) => void;
  executing: boolean;
  validationError?: string;
  canSubmit: boolean;
  workspace: Workspace;
  permissionCanRun: boolean;
  permissionCanAssign?: boolean;
  modelAvailability?: string;
  // Backwards compatibility
  assignments?: Assignment[];
  blueprints?: Blueprint[];
  selectedAssignmentId?: string;
  onSelectAssignment?: (id: string) => void;
}

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
  onCreateAssignment?: () => void;
  onOpenExecution?: () => void;
  canBench?: boolean;
  canApprove?: boolean;
  canPublish?: boolean;
  run?: Run | null;
  assignment?: Assignment;
  auditEvents?: Audit[];
  evaluation?: Evaluation | null;
  executionForm?: ExecutionFormConfig;
}

function RenderExecutionForm({
  executionForm,
}: {
  executionForm: ExecutionFormConfig;
}) {
  return (
    <div className="run-form-wrapper">
      {executionForm.publishedAgents?.length ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            executionForm.onSubmit(e);
          }}
          className="run-form"
          noValidate
        >
          <div className="form-fields">
            <label>
              Penugasan agent
              <select
                aria-label="Penugasan agent"
                value={
                  executionForm.publishedAgents.find(
                    (a) => a.versionId === executionForm.selectedVersionId,
                  )?.assignmentId ||
                  executionForm.selectedVersionId ||
                  ""
                }
                onChange={(e) => {
                  const val = e.target.value;
                  const matched = executionForm.publishedAgents.find(
                    (a) => a.assignmentId === val || a.versionId === val,
                  );
                  if (matched) {
                    executionForm.onSelectVersion(matched.versionId);
                  } else {
                    executionForm.onSelectVersion(val);
                  }
                }}
                disabled={executionForm.executing || executionForm.creatingAssignment}
              >
                <option value="">Pilih penugasan aktif atau agent</option>
                {executionForm.publishedAgents.map((agent) => (
                  <option
                    key={agent.versionId}
                    value={agent.assignmentId || agent.versionId}
                  >
                    {agent.blueprintName} (v{agent.versionNumber}) ·{" "}
                    {agent.isAssigned
                      ? `Siap dijalankan (${agent.roleName})`
                      : "Belum ditugaskan"}
                  </option>
                ))}
              </select>
            </label>

            {(() => {
              const currentAgent = executionForm.publishedAgents.find(
                (a) => a.versionId === executionForm.selectedVersionId,
              );

              if (!currentAgent) {
                return (
                  <Notice tone="info">
                    Pilih salah satu agent yang telah dipublikasikan di atas untuk memulai eksekusi.
                  </Notice>
                );
              }

              if (!currentAgent.isAssigned) {
                return (
                  <div className="inline-assignment-panel">
                    <Notice tone="warning">
                      Agent ini telah dipublikasikan namun belum memiliki penugasan operasional di proyek ini. Tentukan peran penugasan untuk langsung mengaktifkannya tanpa kembali ke Factory.
                    </Notice>
                    <label>
                      Peran / nama penugasan
                      <input
                        aria-label="Peran operasional penugasan"
                        type="text"
                        placeholder="Contoh: Peneliti produk, Analis risiko…"
                        value={executionForm.roleInput}
                        onChange={(e) => executionForm.onRoleInputChange(e.target.value)}
                        disabled={executionForm.creatingAssignment}
                        maxLength={64}
                      />
                    </label>
                    <Button
                      type="button"
                      className="w-full mt-2"
                      onClick={() => void executionForm.onCreateAssignment()}
                      disabled={
                        executionForm.creatingAssignment ||
                        executionForm.roleInput.trim().length < 2 ||
                        executionForm.permissionCanAssign === false
                      }
                    >
                      <Plus size={14} />
                      {executionForm.creatingAssignment
                        ? "Membuat penugasan…"
                        : "Buat Penugasan"}
                    </Button>
                  </div>
                );
              }

              return (
                <>
                  <div className="agent-assignment-badge">
                    <Bot size={15} />
                    <span>
                      Peran: <strong>{currentAgent.roleName}</strong>
                    </span>
                    <span className="mono subtle">({currentAgent.model})</span>
                  </div>

                  <label>
                    Instruksi riset
                    <textarea
                      aria-label="Instruksi riset"
                      placeholder="Contoh: Jelaskan perbedaan likuiditas dan solvabilitas, lalu sebutkan risiko yang perlu diperhatikan tim produk."
                      rows={6}
                      value={executionForm.prompt}
                      maxLength={12000}
                      onChange={(e) => executionForm.onPromptChange(e.target.value)}
                      disabled={executionForm.executing}
                    />
                  </label>

                  <Notice>
                    Instruksi dan konfigurasi agent dikirim melalui ARYN Runtime ke
                    penyedia model jarak jauh yang dipilih.
                  </Notice>

                  <label className="checkbox-field">
                    <input
                      type="checkbox"
                      checked={executionForm.consent}
                      onChange={(e) => executionForm.onConsentChange(e.target.checked)}
                      disabled={executionForm.executing}
                    />
                    Saya menyetujui pengiriman instruksi ini ke model yang dipilih.
                  </label>

                  {executionForm.validationError && (
                    <Notice tone="error">{executionForm.validationError}</Notice>
                  )}
                  {!executionForm.workspace.runtime.ready && (
                    <Notice tone="error">
                      {executionForm.workspace.runtime.message}
                    </Notice>
                  )}
                  {gatewayStatus(executionForm.workspace).tone !== "success" && (
                    <Notice tone={gatewayStatus(executionForm.workspace).tone}>
                      {gatewayStatus(executionForm.workspace).label}
                    </Notice>
                  )}
                  {executionForm.modelAvailability &&
                    executionForm.modelAvailability !== "available" && (
                      <Notice tone="warning">
                        {executionForm.modelAvailability === "unavailable"
                          ? "Model tidak tersedia melalui Model Gateway. Pilih versi dengan model lain sebelum menjalankan agent."
                          : "Ketersediaan model belum dapat diverifikasi. Eksekusi diblokir sampai runtime menyediakan bukti ketersediaan yang valid."}
                      </Notice>
                    )}
                </>
              );
            })()}
          </div>

          {(() => {
            const currentAgent = executionForm.publishedAgents.find(
              (a) => a.versionId === executionForm.selectedVersionId,
            );
            if (!currentAgent || !currentAgent.isAssigned) return null;

            return (
              <div className="run-submit mt-4">
                <span className="text-xs subtle flex items-center gap-1">
                  <ShieldCheck size={13} />
                  Budget dan izin diperiksa Core
                </span>
                <Button
                  className="w-full mt-2"
                  disabled={
                    executionForm.executing ||
                    !executionReady(executionForm.workspace) ||
                    !executionForm.permissionCanRun ||
                    !executionForm.canSubmit
                  }
                >
                  <Workflow size={15} />
                  {executionForm.executing ? "Menjalankan…" : "Jalankan agent"}
                </Button>
              </div>
            );
          })()}
        </form>
      ) : (
        <Notice tone="warning">
          Belum ada agent aktif atau terpublikasi di proyek ini. Selesaikan
          pembuatan versi, Bench, dan persetujuan di Agent Factory.
        </Notice>
      )}
    </div>
  );
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
  onCreateAssignment,
  onOpenExecution,
  canBench = true,
  canApprove = true,
  canPublish = true,
  run,
  assignment,
  auditEvents = [],
  evaluation,
  executionForm,
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

  const standardSuiteScenarios = Object.entries(scenarioNames).map(
    ([scenario_id, name]) => ({
      scenario_id,
      name,
      passed: undefined as boolean | undefined,
      actual_output: "",
      latency_seconds: 0,
      total_tokens: 0,
      actual_model: "",
      failure_reason: undefined as string | undefined,
    }),
  );

  const scenarios = evaluation
    ? evaluation.details.filter(
        (s) =>
          selectedNode?.nodeType !== "scenario" ||
          s.scenario_id === selectedNode.details?.scenarioId,
      )
    : standardSuiteScenarios.filter(
        (s) =>
          selectedNode?.nodeType !== "scenario" ||
          s.scenario_id === selectedNode.details?.scenarioId,
      );

  const isExecutionStandaloneForm = mode === "execution" && executionForm && !run;

  return (
    <section className="canvas-inspector" aria-label="Inspector Node">
      <div className="inspector-header">
        <div className="inspector-title-group">
          <div className="inspector-node-type">
            {mode === "factory"
              ? !version
                ? "BLUEPRINT · BELUM ADA VERSI"
                : draft
                  ? "RANCANGAN LOKAL"
                  : "VERSI TERSIMPAN · HANYA BACA"
              : mode === "execution"
                ? isExecutionStandaloneForm
                  ? "EKSEKUSI RESEARCH AGENT"
                  : "DATA TERSIMPAN · HANYA BACA"
                : !evaluation
                  ? "SKENARIO SUITE · BELUM DIJALANKAN"
                  : "DATA TERSIMPAN · HANYA BACA"}
          </div>
          <h2 className="inspector-title">
            {mode === "factory" && draft
              ? "Rancang Versi Baru"
              : mode === "factory" && !version
                ? "Konfigurasikan Versi Pertama"
                : isExecutionStandaloneForm
                  ? "Form Eksekusi Agent"
                  : mode === "bench" && evaluation
                    ? benchState === "bench_passed"
                      ? "Evaluasi lulus"
                      : benchState === "bench_unverified"
                        ? "Evaluasi tidak terverifikasi"
                        : "Evaluasi belum lulus"
                    : selectedNode?.label || "Pilih node"}
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

      {isExecutionStandaloneForm && executionForm && (
        <div className="inspector-content p-4" tabIndex={0}>
          <RenderExecutionForm executionForm={executionForm} />
        </div>
      )}

      {!isExecutionStandaloneForm && !selectedNode && (
        <div className="inspector-empty-state">
          <Bot size={28} />
          <p>Pilih node menggunakan klik atau keyboard untuk memeriksa data.</p>
        </div>
      )}

      {!isExecutionStandaloneForm && selectedNode && (
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
                      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                        <Status value={run.status} />
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setActiveTab("trace")}
                        >
                          <ShieldCheck size={14} />
                          Audit ({auditEvents?.length || 0})
                        </Button>
                      </div>
                      <div className="usage-row mb-4">
                        <div>
                          <small>Token input</small>
                          <strong className="mono">{number(run.input_tokens)}</strong>
                        </div>
                        <div>
                          <small>Token output</small>
                          <strong className="mono">{number(run.output_tokens)}</strong>
                        </div>
                        <div>
                          <small>Total token</small>
                          <strong className="mono">{number(run.total_tokens)}</strong>
                        </div>
                      </div>
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
                        <dt>Model diminta</dt>
                        <dd className="mono">{run.model || "Tidak dilaporkan"}</dd>
                        <dt>Model aktual</dt>
                        <dd className="mono">{run.actual_model || "Belum tercatat"}</dd>
                        <dt>Model Gateway</dt>
                        <dd>{run.gateway ? "Tercatat pada run" : "Belum tercatat"}</dd>
                        <dt>Backend runtime</dt>
                        <dd>{run.runtime_backend || "Belum tercatat"}</dd>
                        <dt>Provider aktual</dt>
                        <dd>{run.actual_provider || "Tidak dilaporkan"}</dd>
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
                          <InspectorTextBlock
                            label="INSTRUKSI SISTEM VERSI HISTORIS"
                            content={version.system_prompt}
                            subtitle="Instruksi sistem versi historis yang tercatat untuk eksekusi run ini."
                          />
                          <dl className="inspector-meta-list">
                            <dt>Temperature</dt>
                            <dd>{version.temperature}</dd>
                            <dt>Batas token</dt>
                            <dd>{version.max_tokens}</dd>
                          </dl>
                        </>
                      )}
                      <InspectorTextBlock
                        label="INSTRUKSI RUN"
                        content={run.prompt}
                        subtitle="Prompt instruksi yang dikirimkan ke agen untuk eksekusi run ini."
                      />
                      {run.output && (
                        <InspectorTextBlock
                          label="RESPONS TERAKHIR"
                          content={run.output}
                          subtitle="Output yang dilaporkan oleh runtime untuk eksekusi ini."
                        />
                      )}
                      {executionForm && (
                        <div className="inspector-execution-form-section mt-5 pt-4 border-t">
                          <h3 className="text-sm font-semibold mb-3">Eksekusi Baru</h3>
                          <RenderExecutionForm executionForm={executionForm} />
                        </div>
                      )}
                    </>
                  )}
                  {activeTab === "output" && (
                    <>
                      {run.error_message && (
                        <Notice tone="error">{run.error_message}</Notice>
                      )}
                      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                        <div className="usage-row">
                          <div>
                            <small>Token input</small>
                            <strong className="mono">{number(run.input_tokens)}</strong>
                          </div>
                          <div>
                            <small>Token output</small>
                            <strong className="mono">{number(run.output_tokens)}</strong>
                          </div>
                          <div>
                            <small>Total token</small>
                            <strong className="mono">{number(run.total_tokens)}</strong>
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setActiveTab("trace")}
                        >
                          <ShieldCheck size={14} />
                          Audit ({auditEvents?.length || 0})
                        </Button>
                      </div>
                      <InspectorTextBlock
                        label="RESPONS TERSIMPAN"
                        content={run.output}
                        emptyText="Runtime belum memberikan output."
                        subtitle="Respons lengkap yang dihasilkan runtime untuk run ini."
                      />
                    </>
                  )}
                  {activeTab === "trace" && (
                    <>
                      <Notice>
                        Trace runtime tidak tersedia. Jejak audit Core
                        tersimpan berikut adalah peristiwa aplikasi nyata.
                      </Notice>
                      <AuditList events={auditEvents} />
                    </>
                  )}
                </>
              ) : (
                <Notice>
                  Belum ada run dipilih. Gunakan node instruksi run untuk
                  memulai eksekusi.
                </Notice>
              ))}

            {mode === "factory" && (
              <>
                {activeTab === "konfigurasi" && (
                  <>
                    {!version ? (
                      <div>
                        <Notice>
                          Blueprint ini belum dikonfigurasi. Tentukan instruksi
                          sistem, model, dan parameter untuk versi pertamanya.
                        </Notice>
                        {error && <Notice tone="error">{error}</Notice>}
                        {onCreateVersion && (
                          <VersionForm
                            versions={versions}
                            models={workspace?.models || []}
                            previous={undefined}
                            pending={pending}
                            onSubmit={(body) => {
                              void onCreateVersion(body).catch(() => {});
                            }}
                          />
                        )}
                      </div>
                    ) : draft && onCreateVersion ? (
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
                          baca. Perubahan disimpan melalui versi baru.
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
                        <InspectorTextBlock
                          label="INSTRUKSI SISTEM · HANYA BACA"
                          content={version.system_prompt}
                          subtitle="Instruksi sistem tersimpan untuk versi agen ini. Gunakan 'Rancang Versi Baru' jika ingin memodifikasi."
                        />
                        {selectedNode.nodeType === "policy" && (
                          <Notice>
                            Core memeriksa izin, budget, dan confinement ARYN Runtime
                            sebelum dispatch. Status runtime saat ini:{" "}
                            {workspace?.runtime.message || "Belum diperiksa"}
                          </Notice>
                        )}
                        {onCreateVersion && (
                          <Button
                            className="w-full mt-3"
                            disabled={pending}
                            onClick={() => setDraft(true)}
                          >
                            <Plus size={15} />
                            Rancang Versi Baru
                          </Button>
                        )}
                        {(selectedNode.nodeType === "approval" || selectedNode.nodeType === "agent") && (
                          <div className="approval-quick-actions mt-3">
                            {onRunBench && (
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={onRunBench}
                                disabled={!canBench}
                              >
                                <Beaker size={14} />
                                Uji di Bench
                              </Button>
                            )}
                            {onApproveVersion && (
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={onApproveVersion}
                                disabled={!canApprove}
                              >
                                <ShieldCheck size={14} />
                                Tinjau dan setujui
                              </Button>
                            )}
                            {onPublishVersion && (
                              <Button
                                size="sm"
                                onClick={onPublishVersion}
                                disabled={!canPublish}
                              >
                                <ArrowDownToLine size={14} />
                                Publikasikan versi
                              </Button>
                            )}
                          </div>
                        )}
                        {version.status === "published" && version.governance_valid && (
                          <div className="published-next-actions mt-3">
                            <Notice tone="success">
                              Versi ini dipublikasikan dan tidak dapat diubah (immutable). Siap ditugaskan ke proyek.
                            </Notice>
                            <div className="flex gap-2 mt-2 flex-wrap">
                              {onCreateAssignment && (
                                <Button
                                  size="sm"
                                  onClick={onCreateAssignment}
                                >
                                  <Plus size={14} />
                                  Buat Penugasan
                                </Button>
                              )}
                              {onOpenExecution && (
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  onClick={onOpenExecution}
                                >
                                  <Workflow size={14} />
                                  Buka Eksekusi
                                </Button>
                              )}
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </>
                )}

                {activeTab === "integritas" && (
                  <>
                    {!version ? (
                      <Notice>
                        Belum ada versi tersimpan. SHA-256 payload hash dan
                        status tata kelola akan tercatat setelah versi pertama
                        dibuat.
                      </Notice>
                    ) : (
                      <>
                        <Status value={version.status} />
                        <InspectorTextBlock
                          label="HASH KONFIGURASI SHA-256"
                          content={version.payload_hash}
                          subtitle="Hash payload konfigurasi untuk verifikasi integritas versi agen."
                        />
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
              </>
            )}

            {mode === "bench" && (
              <>
                {evaluation ? (
                  <>
                    <div className={`bench-score-banner text-${benchTone}`}>
                      <div className="score-percent">
                        {Math.round(evaluation.score * 100)}%
                      </div>
                      <div>
                        <Status value={benchState} />
                        <p>
                          {evaluation.passed_scenarios}/
                          {evaluation.total_scenarios} skenario tercatat lulus
                        </p>
                      </div>
                    </div>
                    {!evaluation.verified && (
                      <Notice tone="warning">
                        Hasil historis tetap disimpan. Evidence tidak
                        terverifikasi dan tidak dapat dipakai untuk
                        approval/publish.
                      </Notice>
                    )}
                  </>
                ) : (
                  <Notice>
                    Empat skenario suite standar di bawah ini belum dijalankan.
                    Klik "Jalankan Bench" untuk mengevaluasi versi agent.
                  </Notice>
                )}

                {activeTab === "skenario" && (
                  <>
                    {scenarios.map((s) => (
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
                            s.passed === undefined
                              ? "idle"
                              : !s.passed
                                ? "failed"
                                : !evaluation?.verified
                                  ? "bench_unverified"
                                  : "bench_passed"
                          }
                        />
                        {s.failure_reason && (
                          <p className="subtle">
                            {failureReason(s.failure_reason)}
                          </p>
                        )}
                        <dl className="inspector-meta-list">
                          <dt>Model aktual</dt>
                          <dd>{s.actual_model || "Belum dievaluasi"}</dd>
                          <dt>Token</dt>
                          <dd>{number(s.total_tokens || 0)}</dd>
                          <dt>Latensi</dt>
                          <dd>{s.latency_seconds || 0}s</dd>
                        </dl>
                        {selectedNode.nodeType === "scenario" && (
                          <InspectorTextBlock
                            label="RESPONS AKTUAL SKENARIO"
                            content={s.actual_output || (selectedNode.details?.actual_output as string) || ""}
                            emptyText="Belum ada respons tersimpan."
                            subtitle={`Respons aktual skenario ${s.name || s.scenario_id}.`}
                          />
                        )}
                      </div>
                    ))}
                    {onRunBench && (
                      <Button
                        className="w-full mt-3"
                        disabled={pending}
                        onClick={onRunBench}
                      >
                        <Beaker size={14} />
                        Jalankan Bench
                      </Button>
                    )}
                  </>
                )}

                {activeTab === "bukti" && (
                  <>
                    {evaluation ? (
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
                    ) : (
                      <Notice>
                        Belum ada bukti evaluasi tersimpan. Jalankan suite Bench
                        untuk membuat bukti provenance terverifikasi.
                      </Notice>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </>
      )}
    </section>
  );
}
