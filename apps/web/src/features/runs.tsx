import { executionReady, gatewayStatus } from "../lib/studio-state";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, ChevronRight, ShieldCheck, Workflow } from "lucide-react";
import type { Shared, Audit, Run } from "../lib/types";
import { date, number } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Busy, Empty, Notice, PageHeading, Status } from "../components/shared";
import { Panel, AuditList } from "../components/workspace";
import { ArynCanvas } from "../components/canvas/aryn-canvas";
import { buildExecutionNodesAndEdges } from "../components/canvas/canvas-builders";
import { historicalRunContext } from "../lib/studio-state";
import { useReducedMotion } from "../lib/motion";

export function Runs({ data, workspace, pending, act, actStream }: Shared) {
  const [params, setParams] = useSearchParams();
  const active = data.assignments.filter(
    (a) =>
      a.status === "active" &&
      data.versions.some(
        (v) =>
          v.id === a.version_id &&
          v.blueprint_id === a.blueprint_id &&
          v.status === "published" &&
          v.integrity_valid &&
          v.governance_valid,
      ),
  );
  const [assignment, setAssignment] = useState(
    params.get("penugasan") || active[0]?.id || "",
  );
  const [prompt, setPrompt] = useState("");
  const [consent, setConsent] = useState(false);
  const [runKey, setRunKey] = useState(() => crypto.randomUUID());
  const [validation, setValidation] = useState("");
  const [executing, setExecuting] = useState(false);
  const [liveEvent, setLiveEvent] = useState<{ step: string; message?: string } | null>(
    null,
  );
  const reducedMotion = useReducedMotion();
  const selected = params.has("hasil")
    ? data.runs.find((r) => r.id === params.get("hasil"))
    : data.runs[0];
  const historical = historicalRunContext(data, selected?.id);
  const assigned = active.find((a) => a.id === assignment);
  const version = data.versions.find((v) => v.id === assigned?.version_id);
  const modelAvailability =
    workspace.models.find((m) => m.model_id === version?.model)?.availability ||
    "unknown";

  const viewResult = (runId: string) => {
    setParams({ hasil: runId });
    const target = document.getElementById("canvas-inspector");
    if (target) {
      target.scrollIntoView({
        behavior: reducedMotion ? "auto" : "smooth",
        block: "start",
      });
    }
  };

  const submit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (prompt.trim().length < 5 || !assigned || !consent) {
      setValidation(
        "Pilih penugasan, isi instruksi minimal lima karakter, dan konfirmasikan penggunaan model.",
      );
      return;
    }
    setValidation("");
    setExecuting(true);
    setLiveEvent({ step: "run.requested" });

    try {
      const runner = actStream || act;
      const r = await runner(
        "/runs",
        {
          assignment_id: assignment,
          prompt: prompt.trim(),
          idempotency_key: runKey,
          allow_remote_model: consent,
        },
        "Eksekusi selesai. Hasil dan audit tersimpan.",
        (evt: any) => {
          if (!evt) return;
          setLiveEvent({ step: evt.type, message: evt.data?.message });
        },
      );
      const newRunId = String((r as any).run_id || (r as any).id);
      setRunKey(crypto.randomUUID());
      viewResult(newRunId);
    } catch {
      /* Retry preserves idempotency key; edits create a new key. */
    } finally {
      setExecuting(false);
      setLiveEvent(null);
    }
  };

  const { nodes: execNodes, edges: execEdges } = useMemo(() => {
    return buildExecutionNodesAndEdges(
      selected,
      historical.version,
      historical.blueprint?.name,
      liveEvent,
    );
  }, [selected, historical.version, historical.blueprint?.name, liveEvent]);

  const executionFormConfig = useMemo(
    () => ({
      assignments: active,
      blueprints: data.blueprints,
      selectedAssignmentId: assigned?.id || "",
      onSelectAssignment: (id: string) => {
        setAssignment(id);
        setRunKey(crypto.randomUUID());
      },
      prompt,
      onPromptChange: (p: string) => {
        setPrompt(p);
        setRunKey(crypto.randomUUID());
      },
      consent,
      onConsentChange: setConsent,
      onSubmit: submit,
      executing,
      validationError: validation,
      canSubmit:
        !pending &&
        executionReady(workspace) &&
        modelAvailability === "available" &&
        Boolean(data.permissions["run:create"]) &&
        consent &&
        prompt.trim().length >= 5,
      workspace,
      permissionCanRun: Boolean(data.permissions["run:create"]),
    }),
    [
      active,
      data.blueprints,
      assigned?.id,
      prompt,
      consent,
      executing,
      validation,
      pending,
      workspace,
      modelAvailability,
      data.permissions,
    ],
  );

  return (
    <>
      <PageHeading
        eyebrow="OPERASIKAN"
        title="Eksekusi"
        description="Jalankan Research Agent melalui ARYN Core, lalu telusuri hasilnya."
      />
      {executing && (
        <Busy label="Core/ARYN Runtime sedang memproses eksekusi baru. Trace per-node belum tersedia; hasil historis tetap ditampilkan." />
      )}
      {selected && !historical.version && (
        <Notice tone="warning">
          Konfigurasi historis run tidak tersedia. Pilihan form baru tidak
          digunakan sebagai penggantinya.
        </Notice>
      )}
      {historical.version && !historical.version.integrity_valid && (
        <Notice tone="warning">
          Integritas versi historis tidak valid. Konfigurasi tersimpan tidak
          dapat dianggap sebagai bukti konfigurasi saat eksekusi.
        </Notice>
      )}

      <div className="execution-canvas-workspace mb-6">
        <ArynCanvas
          mode="execution"
          initialNodes={execNodes}
          initialEdges={execEdges}
          run={selected}
          version={historical.version}
          assignment={historical.assignment}
          auditEvents={data.audit.filter((e) => e.resource_id === selected?.id)}
          showInspectorByDefault={Boolean(selected)}
          executionForm={executionFormConfig}
        />
      </div>

      {params.has("hasil") && !selected && (
        <Panel title="Hasil eksekusi" className="mb-6">
          <Empty
            title="Run yang dipilih tidak tersedia"
            description="Run tidak ditemukan pada proyek aktif. Pilih run yang tersedia dari riwayat."
          />
        </Panel>
      )}

      {selected && (
        <Panel
          className="run-panel-result mb-6"
          title="Hasil eksekusi"
          subtitle={`${historical.blueprint ? `${historical.blueprint.name} · ` : ""}${historical.assignment ? historical.assignment.role_name : "Run terisolasi"}`}
        >
          <RunResultPanel
            run={selected}
            audit={data.audit.filter((a) => a.resource_id === selected.id)}
          />
        </Panel>
      )}

      <Panel
        className="run-panel-execution mt-6"
        title="Eksekusi agent"
        subtitle="Konfigurasi selalu diambil dari versi yang dipublikasikan."
      >
        {active.length ? (
          <form onSubmit={submit} className="run-form" noValidate>
            <div className="form-fields">
              <label>
                Penugasan agent
                <select
                  value={assigned?.id || ""}
                  onChange={(e) => {
                    setAssignment(e.target.value);
                    setRunKey(crypto.randomUUID());
                  }}
                  disabled={pending || executing}
                >
                  <option value="">Pilih penugasan aktif</option>
                  {active.map((a) => (
                    <option key={a.id} value={a.id}>
                      {
                        data.blueprints.find((b) => b.id === a.blueprint_id)
                          ?.name
                      }{" "}
                      · {a.role_name}
                    </option>
                  ))}
                </select>
              </label>
              {version && (
                <div className="model-scope">
                  <Bot size={15} />
                  <span className="mono">{version.model}</span>
                  <span>v{version.version_number}</span>
                </div>
              )}
              <label>
                Instruksi riset
                <textarea
                  placeholder="Contoh: Jelaskan perbedaan likuiditas dan solvabilitas, lalu sebutkan risiko yang perlu diperhatikan tim produk."
                  rows={6}
                  value={prompt}
                  maxLength={12000}
                  onChange={(e) => {
                    setPrompt(e.target.value);
                    setRunKey(crypto.randomUUID());
                  }}
                  disabled={pending || executing}
                />
              </label>
              <Notice>
                Instruksi dan konfigurasi agent dikirim melalui ARYN Runtime ke
                penyedia model jarak jauh yang dipilih. Gunakan data yang Anda
                izinkan untuk dikirim. Tool host tidak tersedia.
              </Notice>
              <label className="checkbox-field">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                  disabled={pending || executing}
                />
                Saya menyetujui pengiriman instruksi ini ke model yang
                dipilih.
              </label>
              {validation && <Notice tone="error">{validation}</Notice>}
              {!workspace.runtime.ready && (
                <Notice tone="error">{workspace.runtime.message}</Notice>
              )}
              {gatewayStatus(workspace).tone !== "success" && (
                <Notice tone={gatewayStatus(workspace).tone}>
                  {gatewayStatus(workspace).label}
                </Notice>
              )}
              {modelAvailability !== "available" && (
                <Notice tone="warning">
                  {modelAvailability === "unavailable"
                    ? "Model tidak tersedia melalui Model Gateway. Pilih versi dengan model lain sebelum menjalankan agent."
                    : "Ketersediaan model belum dapat diverifikasi. Eksekusi diblokir sampai runtime menyediakan bukti ketersediaan yang valid."}
                </Notice>
              )}
            </div>
            <div className="run-submit">
              <span>
                <ShieldCheck size={14} />
                Budget dan izin diperiksa Core
              </span>
              <Button
                disabled={
                  pending ||
                  executing ||
                  !executionReady(workspace) ||
                  modelAvailability !== "available" ||
                  !data.permissions["run:create"] ||
                  !consent ||
                  prompt.trim().length < 5
                }
              >
                <Workflow size={15} />
                {pending || executing ? "Menjalankan…" : "Jalankan agent"}
              </Button>
            </div>
          </form>
        ) : (
          <Empty
            title="Belum ada agent yang ditugaskan"
            description="Selesaikan Bench, persetujuan, publikasi, dan penugasan di Agent Factory sebelum menjalankan riset."
            action="Buka Agent Factory"
            onAction={() => window.location.assign("/factory")}
          />
        )}
      </Panel>

      <Panel
        className="mt-6"
        title="Riwayat eksekusi"
        subtitle="Tetap tersedia setelah halaman dimuat ulang."
      >
        {data.runs.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Instruksi</th>
                  <th>Status</th>
                  <th>Model</th>
                  <th>Token</th>
                  <th>Waktu</th>
                  <th>
                    <span className="sr-only">Aksi</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.runs.map((r) => {
                  const isCurrent = selected?.id === r.id;
                  return (
                    <tr
                      key={r.id}
                      className={isCurrent ? "table-row-selected" : ""}
                    >
                      <td className="run-prompt-cell">{r.prompt}</td>
                      <td>
                        <Status value={r.status} />
                      </td>
                      <td className="mono">{r.model}</td>
                      <td className="mono">{number(r.total_tokens)}</td>
                      <td className="subtle">{date(r.created_at)}</td>
                      <td>
                        <Button
                          size="sm"
                          variant={isCurrent ? "secondary" : "ghost"}
                          onClick={() => viewResult(r.id)}
                          aria-label={`Lihat hasil eksekusi ${r.id}`}
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
            title="Riwayat masih kosong"
            description="Setiap eksekusi yang dimulai Core akan dicatat beserta status dan hasilnya."
          />
        )}
      </Panel>
    </>
  );
}

function RunResultPanel({ run, audit }: { run: Run; audit: Audit[] }) {
  const [tab, setTab] = useState("output");
  return (
    <div className="run-result-container">
      <div className="result-meta">
        <Status value={run.status} />
        <span className="mono">{run.id}</span>
      </div>
      <div className="result-tabs">
        <button
          aria-pressed={tab === "output"}
          className={tab === "output" ? "selected" : ""}
          onClick={() => setTab("output")}
        >
          Output
        </button>
        <button
          aria-pressed={tab === "audit"}
          className={tab === "audit" ? "selected" : ""}
          onClick={() => setTab("audit")}
        >
          Audit <span>{audit.length}</span>
        </button>
      </div>
      {tab === "output" ? (
        <div className="result-output-wrapper">
          <div className="result-body">
            {run.error_message ? (
              <Notice tone="error">
                Eksekusi gagal. Periksa koneksi ARYN Runtime, model, dan gate
                keamanan server.
              </Notice>
            ) : null}
            <pre className="prompt-output">
              {run.output || "Runtime belum memberikan output."}
            </pre>
          </div>
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
          <dl className="result-info">
            <dt>
              {run.status === "completed" ? "Model aktual" : "Model diminta"}
            </dt>
            <dd className="mono">{run.model}</dd>
            <dt>Provider</dt>
            <dd>{run.provider}</dd>
            <dt>Selesai</dt>
            <dd>{date(run.completed_at)}</dd>
            <dt>Trace runtime</dt>
            <dd>
              Belum tersedia untuk eksekusi langsung; audit Core tersedia.
            </dd>
          </dl>
        </div>
      ) : (
        <div className="result-audit-wrapper">
          <AuditList events={audit} />
        </div>
      )}
    </div>
  );
}
