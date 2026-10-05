import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Bot, ChevronRight, ShieldCheck, Workflow } from "lucide-react";
import type { Run, Audit } from "../lib/types";
import { date, number } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Busy, Empty, Notice, PageHeading, Status } from "../components/shared";
import type { Shared } from "../lib/types";
import { Panel, AuditList } from "../components/workspace";
export function Runs({ data, workspace, pending, act }: Shared) {
  const [params, setParams] = useSearchParams();
  const [assignment, setAssignment] = useState(
    params.get("penugasan") || data.assignments[0]?.id || "",
  );
  const [prompt, setPrompt] = useState("");
  const [consent, setConsent] = useState(false);
  const [runKey, setRunKey] = useState(() => crypto.randomUUID());
  const [validation, setValidation] = useState("");
  const selected =
    data.runs.find((r) => r.id === params.get("hasil")) || data.runs[0];
  const active = data.assignments.filter(
    (a) =>
      a.status === "active" &&
      data.versions.some(
        (v) =>
          v.id === a.version_id &&
          v.blueprint_id === a.blueprint_id &&
          v.status === "published" &&
          v.governance_valid,
      ),
  );
  const assigned = active.find((a) => a.id === assignment);
  const version = data.versions.find((v) => v.id === assigned?.version_id);
  const viewResult = (runId: string) => {
    setParams({ hasil: runId });
    const target = document.getElementById("hasil-eksekusi");
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      target.classList.remove("highlight-pulse");
      void target.offsetWidth;
      target.classList.add("highlight-pulse");
      setTimeout(() => {
        target.classList.remove("highlight-pulse");
      }, 1600);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (prompt.trim().length < 5 || !assigned || !consent) {
      setValidation(
        "Pilih penugasan, isi instruksi minimal lima karakter, dan konfirmasikan penggunaan model.",
      );
      return;
    }
    setValidation("");
    try {
      const r = await act(
        "/runs",
        {
          assignment_id: assignment,
          prompt: prompt.trim(),
          idempotency_key: runKey,
          allow_remote_model: consent,
        },
        "Eksekusi selesai. Hasil dan audit tersimpan.",
      );
      const newRunId = String(r.run_id || r.id);
      setRunKey(crypto.randomUUID());
      viewResult(newRunId);
    } catch {
      /* Retry preserves idempotency key; edits create a new key. */
    }
  };
  return (
    <>
      <PageHeading
        eyebrow="OPERASIKAN"
        title="Eksekusi"
        description="Jalankan Research Agent melalui ARYN Core, lalu telusuri hasilnya."
      />
      <div className="run-layout">
        <Panel
          className="run-panel-execution"
          title="Eksekusi Research Agent"
          subtitle="Konfigurasi selalu diambil dari versi yang dipublikasikan."
        >
          {active.length ? (
            <form onSubmit={submit} className="run-form" noValidate>
              <div className="form-fields">
                <label>
                  Penugasan agent
                  <select
                    value={assignment}
                    onChange={(e) => {
                      setAssignment(e.target.value);
                      setRunKey(crypto.randomUUID());
                    }}
                    disabled={pending}
                  >
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
                    rows={7}
                    value={prompt}
                    maxLength={12000}
                    onChange={(e) => {
                      setPrompt(e.target.value);
                      setRunKey(crypto.randomUUID());
                    }}
                    disabled={pending}
                  />
                </label>
                <Notice>
                  Instruksi dan konfigurasi agent dikirim melalui Hermes ke
                  penyedia model jarak jauh yang dipilih. Gunakan data yang Anda
                  izinkan untuk dikirim. Tool host tidak tersedia.
                </Notice>
                <label className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(e) => setConsent(e.target.checked)}
                    disabled={pending}
                  />
                  Saya menyetujui pengiriman instruksi ini ke model yang
                  dipilih.
                </label>
                {validation && <Notice tone="error">{validation}</Notice>}
                {!workspace.runtime.ready && (
                  <Notice tone="error">{workspace.runtime.message}</Notice>
                )}
                {pending && (
                  <Busy label="Core memproses riset melalui Hermes. Hasil akan tersimpan otomatis…" />
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
                    !workspace.runtime.ready ||
                    !data.permissions["run:create"] ||
                    !consent ||
                    prompt.trim().length < 5
                  }
                >
                  <Workflow size={15} />
                  {pending ? "Menjalankan…" : "Jalankan agent"}
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
          id="hasil-eksekusi"
          className="run-panel-result"
          title="Hasil eksekusi"
          subtitle="Output asli, penggunaan token, dan jejak Core."
          action={
            selected ? (
              <span className="subtle-label active-run-pill">
                AKTIF DITAMPILKAN
              </span>
            ) : undefined
          }
        >
          {selected ? (
            <RunResultPanel
              run={selected}
              audit={data.audit.filter((e) => e.resource_id === selected.id)}
            />
          ) : (
            <Empty
              title="Hasil riset akan muncul di sini"
              description="Belum ada eksekusi pada proyek ini. Output dan jumlah token hanya ditampilkan setelah dilaporkan runtime."
            />
          )}
        </Panel>
      </div>
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
          className={tab === "output" ? "selected" : ""}
          onClick={() => setTab("output")}
        >
          Output
        </button>
        <button
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
                Eksekusi gagal. Periksa koneksi Hermes, model, dan gate keamanan
                server.
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
