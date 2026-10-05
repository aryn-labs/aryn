import { useState } from "react";
import {
  AlertTriangle,
  Beaker,
  Bot,
  Copy,
  Fingerprint,
  Lock,
  Plus,
  ShieldCheck,
  X,
  XCircle,
  CheckCircle2,
} from "lucide-react";
import { Button } from "../ui/button";
import { Status, scenarioNames, failureReason } from "../shared";
import { date, number } from "../../lib/utils";
import type { BaseNodeData, CanvasMode } from "./types";
import type { Audit, Evaluation, Run, Version, Workspace } from "../../lib/types";

interface CanvasInspectorProps {
  mode: CanvasMode;
  selectedNode: BaseNodeData | null;
  onClose: () => void;
  // Factory mode props
  version?: Version | null;
  workspace?: Workspace;
  onNewVersionFromConfig?: (config: {
    systemPrompt: string;
    model: string;
    temperature: number;
    maxTokens: number;
  }) => void;
  onRunBench?: () => void;
  onApproveVersion?: () => void;
  onPublishVersion?: () => void;
  // Execution mode props
  run?: Run | null;
  auditEvents?: Audit[];
  // Bench mode props
  evaluation?: Evaluation | null;
}

export function CanvasInspector({
  mode,
  selectedNode,
  onClose,
  version,
  workspace,
  onNewVersionFromConfig,
  onRunBench,
  onApproveVersion,
  onPublishVersion,
  run,
  auditEvents = [],
  evaluation,
}: CanvasInspectorProps) {
  const [activeTab, setActiveTab] = useState<string>(() => {
    if (mode === "execution") return "detail";
    if (mode === "bench") return "skenario";
    return "konfigurasi";
  });

  const [copied, setCopied] = useState(false);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!selectedNode) {
    return (
      <section className="canvas-inspector canvas-inspector-empty" aria-label="Inspector Node">
        <div className="inspector-empty-state">
          <Bot size={28} className="text-secondary" />
          <div className="inspector-empty-title">Pilih Node</div>
          <p>Klik salah satu node di canvas untuk memeriksa detail, konfigurasi nyata, atau jejak eksekusi.</p>
        </div>
      </section>
    );
  }

  const isPublished = version?.status === "published";

  return (
    <section className="canvas-inspector" aria-label="Inspector Node">
      <div className="inspector-header">
        <div className="inspector-title-group">
          <div className="inspector-node-type">
            <span className="mono uppercase">{selectedNode.nodeType}</span>
            <span className={`status-badge-dot status-${selectedNode.status}`} />
          </div>
          <h3 className="inspector-title">{selectedNode.label}</h3>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Tutup panel inspector"
          onClick={onClose}
        >
          <X size={16} />
        </Button>
      </div>

      {/* Tabs based on mode */}
      <div className="inspector-tabs" role="tablist">
        {mode === "execution" && (
          <>
            <button
              role="tab"
              aria-selected={activeTab === "detail"}
              className={activeTab === "detail" ? "active" : ""}
              onClick={() => setActiveTab("detail")}
            >
              DETAIL
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "output"}
              className={activeTab === "output" ? "active" : ""}
              onClick={() => setActiveTab("output")}
            >
              OUTPUT
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "trace"}
              className={activeTab === "trace" ? "active" : ""}
              onClick={() => setActiveTab("trace")}
            >
              TRACE
            </button>
          </>
        )}

        {mode === "factory" && (
          <>
            <button
              role="tab"
              aria-selected={activeTab === "konfigurasi"}
              className={activeTab === "konfigurasi" ? "active" : ""}
              onClick={() => setActiveTab("konfigurasi")}
            >
              KONFIGURASI
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "integritas"}
              className={activeTab === "integritas" ? "active" : ""}
              onClick={() => setActiveTab("integritas")}
            >
              TATA KELOLA
            </button>
          </>
        )}

        {mode === "bench" && (
          <>
            <button
              role="tab"
              aria-selected={activeTab === "skenario"}
              className={activeTab === "skenario" ? "active" : ""}
              onClick={() => setActiveTab("skenario")}
            >
              SKENARIO
            </button>
            <button
              role="tab"
              aria-selected={activeTab === "bukti"}
              className={activeTab === "bukti" ? "active" : ""}
              onClick={() => setActiveTab("bukti")}
            >
              BUKTI BENCH
            </button>
          </>
        )}
      </div>

      <div className="inspector-content">
        {/* ======================= EXECUTION MODE ======================= */}
        {mode === "execution" && run && (
          <>
            {activeTab === "detail" && (
              <div className="inspector-panel-detail">
                <div className="inspector-status-card">
                  <div className="status-row">
                    <span className="subtle-label">STATUS</span>
                    <Status value={run.status} />
                  </div>
                  <div className="metrics-grid">
                    <div className="metric-box">
                      <small>TOTAL TOKEN</small>
                      <strong className="mono">{number(run.total_tokens || 0)}</strong>
                    </div>
                    <div className="metric-box">
                      <small>TOKEN INPUT</small>
                      <strong className="mono">{number(run.input_tokens || 0)}</strong>
                    </div>
                    <div className="metric-box">
                      <small>TOKEN OUTPUT</small>
                      <strong className="mono">{number(run.output_tokens || 0)}</strong>
                    </div>
                  </div>
                </div>

                <div className="inspector-section">
                  <div className="field-caption">IDENTITAS CORE</div>
                  <dl className="inspector-meta-list">
                    <dt>Core Run ID</dt>
                    <dd className="mono text-wrap">{run.id}</dd>
                    <dt>Session ID</dt>
                    <dd className="mono text-wrap">{run.session_id}</dd>
                    <dt>Model</dt>
                    <dd className="mono">{run.model}</dd>
                    <dt>Provider</dt>
                    <dd>{run.provider}</dd>
                    <dt>Dibuat</dt>
                    <dd>{date(run.created_at)}</dd>
                    {run.completed_at && (
                      <>
                        <dt>Selesai</dt>
                        <dd>{date(run.completed_at)}</dd>
                      </>
                    )}
                  </dl>
                </div>

                <div className="inspector-section">
                  <div className="field-caption">INSTRUKSI INPUT</div>
                  <pre className="inspector-code-block">{run.prompt}</pre>
                </div>
              </div>
            )}

            {activeTab === "output" && (
              <div className="inspector-panel-output">
                {run.error_message && (
                  <div className="inspector-notice notice-error">
                    <AlertTriangle size={15} />
                    <span>{run.error_message}</span>
                  </div>
                )}
                <div className="field-caption">RESPONS RUNTIME</div>
                <div className="inspector-output-box">
                  <pre className="inspector-code-block whitespace-pre-wrap">
                    {run.output || "Runtime belum memberikan output."}
                  </pre>
                  {run.output && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="copy-btn"
                      onClick={() => copyToClipboard(run.output)}
                    >
                      <Copy size={13} />
                      {copied ? "Tersalin" : "Salin output"}
                    </Button>
                  )}
                </div>
              </div>
            )}

            {activeTab === "trace" && (
              <div className="inspector-panel-trace">
                <div className="inspector-notice notice-info">
                  <ShieldCheck size={15} />
                  <span>
                    Trace runtime Hermes: Tidak tersedia untuk eksekusi langsung.
                    Jejak peristiwa audit Core tercatat di bawah secara kriptografis.
                  </span>
                </div>
                <div className="field-caption">JEJAK PERISTIWA CORE ({auditEvents.length})</div>
                {auditEvents.length > 0 ? (
                  <div className="audit-timeline">
                    {auditEvents.map((evt) => (
                      <div key={evt.id} className="audit-timeline-item">
                        <div className="timeline-marker" />
                        <div className="timeline-content">
                          <strong className="mono">{evt.event_type}</strong>
                          <span className="mono subtle text-xs">{evt.id}</span>
                          <span className="subtle text-xs">{date(evt.occurred_at)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="subtle text-sm">Belum ada peristiwa audit untuk run ini.</p>
                )}
              </div>
            )}
          </>
        )}

        {/* ======================= FACTORY MODE ======================= */}
        {mode === "factory" && version && (
          <>
            {activeTab === "konfigurasi" && (
              <div className="inspector-panel-config">
                {isPublished && (
                  <div className="inspector-notice notice-locked">
                    <Lock size={15} />
                    <div>
                      <strong>Versi Dipublikasikan (Immutable)</strong>
                      <p>
                        Versi ini terkunci dan tidak dapat diubah langsung demi tata kelola Core.
                        Gunakan tombol di bawah untuk membuat versi baru dari konfigurasi ini.
                      </p>
                    </div>
                  </div>
                )}

                {selectedNode.nodeType === "model" && (
                  <div className="inspector-section">
                    <div className="field-caption">PILIHAN MODEL & PARAMETER</div>
                    <div className="config-item">
                      <label>Model yang Dipilih</label>
                      <input
                        type="text"
                        className="mono"
                        disabled
                        value={version.model}
                      />
                    </div>
                    <div className="config-item">
                      <label>Temperature ({version.temperature})</label>
                      <input
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        disabled={isPublished}
                        value={version.temperature}
                        readOnly
                      />
                    </div>
                    <div className="config-item">
                      <label>Batas Token (Max Tokens)</label>
                      <input
                        type="number"
                        className="mono"
                        disabled
                        value={version.max_tokens}
                      />
                    </div>
                    <div className="config-item">
                      <label>Kesiapan Provider</label>
                      <span className="provider-status-badge">
                        {workspace?.models.find((m) => m.model_id === version.model)?.availability === "available"
                          ? "Tersedia di Hermes & Model Router"
                          : "Model tidak siap atau belum terverifikasi"}
                      </span>
                    </div>
                  </div>
                )}

                {selectedNode.nodeType === "agent" && (
                  <div className="inspector-section">
                    <div className="field-caption">INSTRUKSI SISTEM (PROMPT)</div>
                    <textarea
                      rows={8}
                      disabled={isPublished}
                      value={version.system_prompt}
                      readOnly
                      className="inspector-textarea mono"
                    />
                    <small className="subtle">
                      {version.system_prompt.length} karakter · Instruksi dasar agen riset
                    </small>
                  </div>
                )}

                {selectedNode.nodeType === "policy" && (
                  <div className="inspector-section">
                    <div className="field-caption">BATAS KEBIJAKAN & GOVERNANCE</div>
                    <div className="policy-box">
                      <ShieldCheck size={16} className="text-success" />
                      <div>
                        <strong>Confinement Terisolasi</strong>
                        <p>Seluruh toolset host nonaktif. Hanya turn teks langsung ke Hermes yang diizinkan.</p>
                      </div>
                    </div>
                    <div className="policy-box mt-3">
                      <Fingerprint size={16} className="text-secondary" />
                      <div>
                        <strong>Integritas Kriptografis</strong>
                        <p>Konfigurasi diproteksi hash SHA-256 dan divalidasi oleh Core.</p>
                      </div>
                    </div>
                  </div>
                )}

                {selectedNode.nodeType === "approval" && (
                  <div className="inspector-section">
                    <div className="field-caption">STATUS PERSETUJUAN</div>
                    <dl className="inspector-meta-list">
                      <dt>Status Versi</dt>
                      <dd><Status value={version.status} /></dd>
                      <dt>Bench Lulus</dt>
                      <dd>{version.bench_eligible ? "Ya (100% Lulus)" : "Belum Lulus"}</dd>
                      <dt>Governance Valid</dt>
                      <dd>{version.governance_valid ? "Terverifikasi" : "Belum / Tidak Valid"}</dd>
                    </dl>
                    <div className="approval-quick-actions mt-3 flex flex-col gap-2">
                      {!version.bench_eligible && onRunBench && (
                        <Button variant="secondary" size="sm" onClick={onRunBench}>
                          <Beaker size={14} /> Jalankan Bench
                        </Button>
                      )}
                      {version.bench_eligible && version.status === "draft" && onApproveVersion && (
                        <Button variant="secondary" size="sm" onClick={onApproveVersion}>
                          <ShieldCheck size={14} /> Tinjau dan Setujui
                        </Button>
                      )}
                      {version.status === "approved" && onPublishVersion && (
                        <Button size="sm" onClick={onPublishVersion}>
                          Publikasikan Versi
                        </Button>
                      )}
                    </div>
                  </div>
                )}

                {isPublished && onNewVersionFromConfig && (
                  <div className="inspector-actions mt-4">
                    <Button
                      className="w-full btn-studio-primary"
                      onClick={() =>
                        onNewVersionFromConfig({
                          systemPrompt: version.system_prompt,
                          model: version.model,
                          temperature: version.temperature,
                          maxTokens: version.max_tokens,
                        })
                      }
                    >
                      <Plus size={15} />
                      Buat Versi Baru Dari Konfigurasi Ini
                    </Button>
                  </div>
                )}
              </div>
            )}

            {activeTab === "integritas" && (
              <div className="inspector-panel-governance">
                <div className="field-caption">PAYLOAD HASH SHA-256</div>
                <div className="hash-display mono break-all">
                  {version.payload_hash}
                </div>
                <dl className="inspector-meta-list mt-4">
                  <dt>Integritas Valid</dt>
                  <dd>{version.integrity_valid ? "Ya" : "Tidak Valid"}</dd>
                  <dt>Dibuat Pada</dt>
                  <dd>{date(version.created_at)}</dd>
                  <dt>Versi Number</dt>
                  <dd className="mono">v{version.version_number}</dd>
                </dl>
              </div>
            )}
          </>
        )}

        {/* ======================= BENCH MODE ======================= */}
        {mode === "bench" && evaluation && (
          <>
            {activeTab === "skenario" && (
              <div className="inspector-panel-scenarios">
                <div className="bench-score-banner">
                  <div className="score-percent">
                    {Math.round(evaluation.score * 100)}%
                  </div>
                  <div>
                    <strong>
                      {evaluation.passed_scenarios}/{evaluation.total_scenarios} Skenario Lulus
                    </strong>
                    <p className="subtle text-xs">
                      {evaluation.verified ? "Bukti Terverifikasi Core" : "Hasil Historis (Tidak Terverifikasi)"}
                    </p>
                  </div>
                </div>

                <div className="field-caption">DETAIL SKENARIO EVALUASI</div>
                <div className="scenario-item-list">
                  {evaluation.details.map((s, idx) => (
                    <div key={s.scenario_id} className={`scenario-inspector-item ${s.passed ? "item-pass" : "item-fail"}`}>
                      <div className="scenario-item-header">
                        <div className="scenario-title">
                          <span className="scenario-idx mono">0{idx + 1}</span>
                          <strong>{scenarioNames[s.scenario_id] || s.name || s.scenario_id}</strong>
                        </div>
                        {s.passed ? (
                          <span className="badge-pass"><CheckCircle2 size={13} /> LULUS</span>
                        ) : (
                          <span className="badge-fail"><XCircle size={13} /> GAGAL</span>
                        )}
                      </div>
                      <div className="scenario-item-meta">
                        <span>Latensi: {s.latency_seconds}s</span>
                        <span>Token: {number(s.total_tokens || 0)}</span>
                        <span className="mono">{s.actual_model}</span>
                      </div>
                      {s.failure_reason && (
                        <div className="scenario-fail-reason">
                          <AlertTriangle size={13} />
                          <span>{failureReason(s.failure_reason)}</span>
                        </div>
                      )}
                      {s.actual_output && (
                        <div className="scenario-output-preview">
                          <small>Respons Model:</small>
                          <pre className="inspector-code-block">{s.actual_output}</pre>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeTab === "bukti" && (
              <div className="inspector-panel-provenance">
                <div className="field-caption">PROVENANCE & INTEGRITAS BUKTI</div>
                <dl className="inspector-meta-list">
                  <dt>Evaluation ID</dt>
                  <dd className="mono break-all">{evaluation.id}</dd>
                  <dt>Model Diminta</dt>
                  <dd className="mono">{evaluation.provenance?.requested_model || "—"}</dd>
                  <dt>Versi Evaluasi</dt>
                  <dd className="mono">{evaluation.provenance?.evaluation_version || "—"}</dd>
                  <dt>Payload Hash</dt>
                  <dd className="mono break-all">{evaluation.provenance?.payload_hash || "—"}</dd>
                  <dt>Dievaluasi Pada</dt>
                  <dd>{date(evaluation.evaluated_at)}</dd>
                </dl>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
