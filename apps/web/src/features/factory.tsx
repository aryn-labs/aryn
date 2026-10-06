import { executionReady, gatewayStatus } from "../lib/studio-state";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Beaker,
  Bot,
  ChevronRight,
  Fingerprint,
  Folder,
  GitBranch,
  Layers3,
  Plus,
  Search,
  ShieldCheck,
} from "lucide-react";
import type { Blueprint } from "../lib/types";
import { date, number } from "../lib/utils";
import { Button } from "../components/ui/button";
import { Modal } from "../components/ui/dialog";
import {
  Busy,
  Empty,
  Notice,
  PageHeading,
  Status,
  scenarioNames,
} from "../components/shared";
import type { Shared } from "../lib/types";
import { Panel, Lifecycle, AuditList } from "../components/workspace";
import { EvaluationPanel, evaluationStatus } from "./bench";
import { VersionForm } from "../components/version-form";
import { ArynCanvas } from "../components/canvas/aryn-canvas";
import { buildFactoryNodesAndEdges } from "../components/canvas/canvas-builders";
export function Factory({ data, openBlueprint }: Shared) {
  const [search, setSearch] = useState("");
  const navigate = useNavigate();
  const list = data.blueprints.filter((b) =>
    `${b.name} ${b.slug} ${b.description}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <>
      <PageHeading
        eyebrow="DEFINISIKAN"
        title="Agent Factory"
        description="Blueprint yang jelas. Versi yang tetap. Agent yang dapat dipertanggungjawabkan."
      >
        <Button
          onClick={openBlueprint}
          disabled={!data.permissions["run:create"]}
        >
          <Plus size={16} />
          Buat blueprint
        </Button>
      </PageHeading>
      <div className="list-toolbar">
        <div className="search-field">
          <Search size={16} />
          <input
            aria-label="Cari blueprint"
            placeholder="Cari nama, slug, atau deskripsi…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <span>{number(list.length)} blueprint</span>
      </div>
      <Panel
        title="Blueprint agent"
        subtitle="Setiap blueprint memiliki versi dan penugasan terpisah."
      >
        {list.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Versi terbaru</th>
                  <th>Status</th>
                  <th>Penugasan</th>
                  <th>Dibuat</th>
                  <th>
                    <span className="sr-only">Buka</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.map((bp) => {
                  const v = data.versions.find((v) => v.blueprint_id === bp.id);
                  return (
                    <tr key={bp.id}>
                      <td>
                        <Link className="table-agent" to={`/factory/${bp.id}`}>
                          <div className="agent-icon">
                            <Bot size={18} />
                          </div>
                          <div>
                            <strong>{bp.name}</strong>
                            <small>{bp.description || bp.slug}</small>
                          </div>
                        </Link>
                      </td>
                      <td className="mono">
                        {v ? `v${v.version_number}` : "—"}
                      </td>
                      <td>
                        {v ? (
                          <Status value={v.status} />
                        ) : (
                          <span className="subtle">Belum dikonfigurasi</span>
                        )}
                      </td>
                      <td>
                        {
                          data.assignments.filter(
                            (a) => a.blueprint_id === bp.id,
                          ).length
                        }
                      </td>
                      <td className="subtle">{date(bp.created_at)}</td>
                      <td>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Buka ${bp.name}`}
                          onClick={() => navigate(`/factory/${bp.id}`)}
                        >
                          <ChevronRight size={16} />
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
            title={
              search
                ? "Tidak ada blueprint yang cocok"
                : "Belum ada blueprint agent"
            }
            description={
              search
                ? "Coba kata pencarian lain atau hapus pencarian."
                : "Mulai dengan tujuan agent. Anda akan mengatur model dan instruksi pada versi pertamanya."
            }
            action={search ? "Hapus pencarian" : "Buat blueprint"}
            onAction={() => (search ? setSearch("") : openBlueprint())}
          />
        )}
      </Panel>
      <div className="page-footnote">
        <Layers3 size={15} />
        Blueprint, versi, dan penugasan dikelola sebagai sumber daya yang
        berbeda.
      </div>
    </>
  );
}

export function AgentDetail({
  data,
  workspace,
  blueprint,
  project,
  pending,
  act,
  error,
  resetError,
}: Shared & { blueprint: Blueprint }) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const versions = data.versions.filter((v) => v.blueprint_id === blueprint.id);
  const selected =
    versions.find((v) => v.id === params.get("versi")) || versions[0];
  const tab = params.get("tab") || "configuration";
  const [dialog, setDialog] = useState("");
  const openDialog = (name: string) => {
    resetError();
    setDialog(name);
  };
  const [role, setRole] = useState("Peneliti produk");
  const [comments, setComments] = useState("");
  const [consent, setConsent] = useState(false);
  const evaluation =
    selected && data.evaluations.find((e) => e.version_id === selected.id);
  const assignment =
    selected && data.assignments.find((a) => a.version_id === selected.id);
  const passed = !!selected?.bench_eligible;
  const modelAvailability =
    workspace.models.find((m) => m.model_id === selected?.model)
      ?.availability || "unknown";
  const modelReady = modelAvailability === "available";
  const stage = !selected
    ? 1
    : assignment
      ? 6
      : selected.status === "published"
        ? 5
        : selected.status === "approved"
          ? 4
          : passed
            ? 3
            : 2;
  const changeTab = (tab: string) => {
    const p = new URLSearchParams(params);
    p.set("tab", tab);
    setParams(p);
  };
  const { nodes: factoryNodes, edges: factoryEdges } = useMemo(() => {
    return buildFactoryNodesAndEdges(blueprint, selected, workspace, project);
  }, [blueprint, selected, workspace, project]);
  const canBench =
    !pending &&
    executionReady(workspace) &&
    modelReady &&
    selected?.integrity_valid &&
    ["draft", "rejected"].includes(selected.status) &&
    data.permissions["run:create"];
  const canApprove =
    !pending &&
    selected?.status === "draft" &&
    passed &&
    selected.integrity_valid &&
    data.permissions["version:approve"];
  const canPublish =
    !pending &&
    selected?.status === "approved" &&
    selected.governance_valid &&
    passed &&
    data.permissions["version:publish"];
  const saveVersion = async (body: unknown) => {
    const v = await act(
      `/blueprints/${blueprint.id}/versions`,
      body,
      "Versi baru tersimpan di database.",
    );
    setDialog("");
    setParams({ versi: String(v.id), tab: "configuration" });
  };
  const runAction = async (kind: string) => {
    if (!selected) return;
    try {
      await act(
        `/versions/${selected.id}/${kind}`,
        kind === "bench"
          ? { allow_remote_model: consent }
          : kind === "approve"
            ? { comments, payload_hash: selected.payload_hash }
            : {},
        kind === "bench"
          ? "Bench selesai. Periksa seluruh hasil skenario."
          : kind === "approve"
            ? "Persetujuan Core tercatat."
            : "Versi berhasil dipublikasikan.",
      );
      setDialog("");
      if (kind === "bench") changeTab("bench");
    } catch {
      /* error is shown above page */
    }
  };
  return (
    <>
      <Link to="/factory" className="back-link">
        <ArrowLeft size={14} />
        Semua blueprint
      </Link>
      <PageHeading
        eyebrow="BLUEPRINT AGENT"
        title={blueprint.name}
        description={
          blueprint.description ||
          "Agent riset teks dengan evaluasi keselamatan dan tata kelola Core."
        }
      >
        <Button
          variant="secondary"
          disabled={pending || !data.permissions["run:create"]}
          onClick={() => openDialog("version")}
        >
          <Plus size={15} />
          Versi baru
        </Button>
      </PageHeading>
      <div className="detail-toolbar">
        <div className="version-picker">
          <GitBranch size={16} />
          <select
            aria-label="Pilih versi agent"
            value={selected?.id || ""}
            onChange={(e) => {
              const p = new URLSearchParams(params);
              p.set("versi", e.target.value);
              setParams(p);
            }}
          >
            {versions.length ? (
              versions.map((v) => (
                <option key={v.id} value={v.id}>
                  v{v.version_number}
                </option>
              ))
            ) : (
              <option value="">Belum ada versi</option>
            )}
          </select>
          {selected && <Status value={selected.status} />}
        </div>
        <span className="mono subtle">{blueprint.id}</span>
      </div>
      {selected &&
        (!selected.integrity_valid ||
          (selected.status === "published" && !selected.governance_valid)) && (
          <Notice tone="error">
            Integritas atau bukti tata kelola versi tidak valid. Buat versi
            baru, jalankan Bench, dan setujui kembali.
          </Notice>
        )}
      <div className="lifecycle-panel">
        <Lifecycle current={stage} />
      </div>
      {selected && !modelReady && (
        <Notice tone="warning">
          {modelAvailability === "unavailable"
            ? "Model tidak tersedia melalui Model Gateway. Pilih model lain pada versi baru sebelum menjalankan Bench."
            : "Ketersediaan model belum dapat diverifikasi. Bench diblokir sampai runtime menyediakan bukti ketersediaan yang valid."}
        </Notice>
      )}
      {gatewayStatus(workspace).tone !== "success" && (
        <Notice tone={gatewayStatus(workspace).tone}>
          {gatewayStatus(workspace).label}
        </Notice>
      )}
      {!selected ? (
        <Panel title="Konfigurasikan versi pertama">
          <Empty
            title="Blueprint siap. Tentukan cara agent bekerja."
            description="Atur instruksi sistem, model, dan batas token. Setiap konfigurasi disimpan sebagai versi baru agar persetujuan tetap dapat ditelusuri."
            action="Buat versi pertama"
            onAction={() => openDialog("version")}
          />
        </Panel>
      ) : (
        <>
          <div className="tabs" role="tablist" aria-label="Detail agent">
            {[
              ["configuration", "Konfigurasi"],
              ["bench", "Hasil Bench"],
              ["assignment", "Penugasan"],
              ["audit", "Audit"],
            ].map(([id, label]) => (
              <button
                key={id}
                role="tab"
                id={`tab-${id}`}
                aria-controls="agent-tab-panel"
                aria-selected={tab === id}
                tabIndex={tab === id ? 0 : -1}
                onClick={() => changeTab(id)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
                    e.preventDefault();
                    const ids = [
                      "configuration",
                      "bench",
                      "assignment",
                      "audit",
                    ];
                    const next =
                      ids[
                        (ids.indexOf(tab) + (e.key === "ArrowRight" ? 1 : 3)) %
                          4
                      ];
                    changeTab(next);
                    document.getElementById(`tab-${next}`)?.focus();
                  }
                }}
              >
                {label}
                {id === "bench" && evaluation && (
                  <span
                    className={`tab-dot ${evaluationStatus(evaluation) === "bench_unverified" ? "warning" : evaluationStatus(evaluation) === "bench_passed" ? "success" : "error"}`}
                  />
                )}
              </button>
            ))}
          </div>
          <div
            role="tabpanel"
            id="agent-tab-panel"
            aria-labelledby={`tab-${tab}`}
          >
            {tab === "configuration" ? (
              <>
                <ArynCanvas
                  mode="factory"
                  initialNodes={factoryNodes}
                  initialEdges={factoryEdges}
                  version={selected}
                  workspace={workspace}
                  showInspectorByDefault
                  versions={versions}
                  pending={pending}
                  error={error}
                  onCreateVersion={
                    data.permissions["run:create"] ? saveVersion : undefined
                  }
                  onRunBench={
                    canBench
                      ? () => {
                          setConsent(false);
                          openDialog("bench");
                        }
                      : undefined
                  }
                  onApproveVersion={
                    canApprove
                      ? () => {
                          setComments("");
                          openDialog("approve");
                        }
                      : undefined
                  }
                  onPublishVersion={
                    canPublish
                      ? () => {
                          openDialog("publish");
                        }
                      : undefined
                  }
                />
                <div className="detail-layout">
                  <Panel
                    title="Instruksi dan model"
                    subtitle="Konfigurasi tersimpan. Perubahan dibuat melalui versi baru."
                    action={
                      <span className="subtle-label">TETAP PER VERSI</span>
                    }
                  >
                    <div className="configuration-content">
                      <div className="field-caption">INSTRUKSI SISTEM</div>
                      <pre className="prompt-output">
                        {selected.system_prompt}
                      </pre>
                      <div className="config-grid">
                        <div>
                          <small>Model yang dipilih</small>
                          <strong className="mono">{selected.model}</strong>
                        </div>
                        <div>
                          <small>Temperature</small>
                          <strong>{selected.temperature}</strong>
                        </div>
                        <div>
                          <small>Batas output</small>
                          <strong>{number(selected.max_tokens)} token</strong>
                        </div>
                        <div>
                          <small>Tool runtime</small>
                          <strong>Tanpa tool · teks saja</strong>
                        </div>
                      </div>
                    </div>
                    <div className="hash-block">
                      <Fingerprint size={16} />
                      <div>
                        <small>SHA-256 konfigurasi</small>
                        <code className="wrap">{selected.payload_hash}</code>
                      </div>
                    </div>
                  </Panel>
                  <div>
                    <Panel
                      title="Langkah berikutnya"
                      subtitle="Core memeriksa setiap persyaratan."
                    >
                      <div className="next-actions">
                        <div>
                          <Beaker size={19} />
                          <div>
                            <h3>Evaluasi dengan Bench</h3>
                            <p>
                              Empat skenario keselamatan dan kualitas. Syarat
                              lulus: 100%.
                            </p>
                          </div>
                        </div>
                        <Button
                          variant="secondary"
                          onClick={() => {
                            setConsent(false);
                            openDialog("bench");
                          }}
                          disabled={
                            pending ||
                            !executionReady(workspace) ||
                            !modelReady ||
                            !selected.integrity_valid ||
                            !["draft", "rejected"].includes(selected.status) ||
                            !data.permissions["run:create"]
                          }
                        >
                          <Beaker size={15} />
                          Jalankan Bench
                        </Button>
                        {!workspace.runtime.ready && (
                          <p className="text-warning">
                            ARYN Runtime belum siap. Periksa Pengaturan.
                          </p>
                        )}
                        <hr />
                        <div>
                          <ShieldCheck size={19} />
                          <div>
                            <h3>Persetujuan manusia</h3>
                            <p>
                              Terikat pada hash versi dan evaluasi terakhir yang
                              lulus.
                            </p>
                          </div>
                        </div>
                        <Button
                          variant="secondary"
                          onClick={() => {
                            setComments("");
                            openDialog("approve");
                          }}
                          disabled={
                            pending ||
                            !passed ||
                            selected.status !== "draft" ||
                            !data.permissions["version:approve"]
                          }
                        >
                          <ShieldCheck size={15} />
                          Tinjau dan setujui
                        </Button>
                        <Button
                          onClick={() => openDialog("publish")}
                          disabled={
                            pending ||
                            selected.status !== "approved" ||
                            !selected.governance_valid ||
                            !passed ||
                            !data.permissions["version:publish"]
                          }
                        >
                          <ArrowDownToLine size={15} />
                          Publikasikan versi
                        </Button>
                      </div>
                    </Panel>
                    {selected.status === "published" &&
                      selected.governance_valid && (
                        <div className="mt-6">
                          <Notice tone="success">
                            Versi ini dipublikasikan dan tidak dapat diubah.
                            Lanjutkan ke penugasan.
                          </Notice>
                          <Button
                            className="mt-4"
                            onClick={() => changeTab("assignment")}
                            variant="secondary"
                          >
                            Atur penugasan
                            <ArrowRight size={15} />
                          </Button>
                        </div>
                      )}
                  </div>
                </div>
              </>
            ) : tab === "bench" ? (
              <>
                <div className="section-actions">
                  <p>
                    Evaluasi untuk{" "}
                    <span className="mono">v{selected.version_number}</span>
                  </p>
                  <Button
                    disabled={
                      pending ||
                      !executionReady(workspace) ||
                      !modelReady ||
                      !selected.integrity_valid ||
                      !["draft", "rejected"].includes(selected.status) ||
                      !data.permissions["run:create"]
                    }
                    onClick={() => {
                      setConsent(false);
                      openDialog("bench");
                    }}
                  >
                    <Beaker size={15} />
                    Jalankan Bench
                  </Button>
                </div>
                {evaluation ? (
                  <EvaluationPanel evaluation={evaluation} />
                ) : (
                  <Panel title="Hasil evaluasi">
                    <Empty
                      title="Versi ini belum dievaluasi"
                      description="Bench menjalankan empat skenario pada model pilihan melalui ARYN Runtime. Tidak ada skor yang dibuat sebelum evaluasi nyata."
                    />
                  </Panel>
                )}
              </>
            ) : tab === "assignment" ? (
              <Panel
                title="Penugasan operasional"
                subtitle={`Lingkup: ${workspace.projects.find((p) => p.id === project)?.name || "proyek ini"}`}
                action={
                  <Button
                    disabled={
                      pending ||
                      selected.status !== "published" ||
                      !selected.governance_valid ||
                      !data.permissions["agent:assign"]
                    }
                    onClick={() => openDialog("assign")}
                  >
                    <Plus size={15} />
                    Buat penugasan
                  </Button>
                }
              >
                {selected.status !== "published" ||
                !selected.governance_valid ? (
                  <Empty
                    title="Publikasikan versi terlebih dahulu"
                    description="Core menolak penugasan versi yang belum dipublikasikan. Selesaikan Bench, persetujuan, dan publikasi."
                    action="Buka konfigurasi"
                    onAction={() => changeTab("configuration")}
                  />
                ) : data.assignments.filter((a) => a.version_id === selected.id)
                    .length ? (
                  <div className="assignment-list">
                    {data.assignments
                      .filter((a) => a.version_id === selected.id)
                      .map((a) => (
                        <div key={a.id}>
                          <div className="agent-icon">
                            <Folder size={18} />
                          </div>
                          <div>
                            <strong>{a.role_name}</strong>
                            <small className="mono">{a.id}</small>
                          </div>
                          <Status value={a.status} />
                          <Button
                            variant="secondary"
                            onClick={() => navigate(`/runs?penugasan=${a.id}`)}
                          >
                            Buka Eksekusi
                            <ArrowRight size={14} />
                          </Button>
                        </div>
                      ))}
                  </div>
                ) : (
                  <Empty
                    title="Siap ditugaskan ke proyek"
                    description="Berikan peran operasional pada versi yang dipublikasikan. Penugasan hanya berlaku dalam proyek yang diizinkan."
                    action="Buat penugasan"
                    onAction={() => openDialog("assign")}
                  />
                )}
              </Panel>
            ) : (
              <Panel
                title="Jejak audit agent"
                subtitle="Peristiwa aktual dari Core dan Factory."
              >
                <AuditList
                  events={data.audit.filter((e) =>
                    [
                      blueprint.id,
                      selected.id,
                      ...data.assignments
                        .filter((a) => a.blueprint_id === blueprint.id)
                        .map((a) => a.id),
                    ].includes(e.resource_id),
                  )}
                />
              </Panel>
            )}
          </div>
        </>
      )}
      <Modal
        open={!!dialog}
        busy={pending}
        onOpenChange={(v) => {
          if (!pending && !v) setDialog("");
        }}
        title={
          dialog === "version"
            ? "Simpan versi baru"
            : dialog === "bench"
              ? "Evaluasi versi dengan Bench"
              : dialog === "approve"
                ? "Tinjau persetujuan versi"
                : dialog === "publish"
                  ? "Publikasikan versi agent"
                  : "Buat penugasan agent"
        }
        description={
          dialog === "version"
            ? "Versi baru memiliki hash konfigurasi sendiri dan harus dievaluasi kembali."
            : dialog === "bench"
              ? "Empat skenario tetap, model nyata, dan tanpa tool host."
              : dialog === "approve"
                ? "Anda bertindak sebagai admin development lokal."
                : dialog === "publish"
                  ? "Publikasi membuat versi tetap dan tersedia untuk penugasan."
                  : "Penugasan dibuat pada proyek aktif dengan otorisasi Core."
        }
      >
        {error && (
          <div className="modal-error">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
        {dialog === "version" ? (
          <VersionForm
            versions={versions}
            models={workspace.models}
            previous={selected}
            pending={pending}
            onSubmit={async (body) => {
              try {
                await saveVersion(body);
              } catch {
                /* visible error */
              }
            }}
          />
        ) : dialog === "assign" ? (
          <form
            noValidate
            onSubmit={async (e) => {
              e.preventDefault();
              if (!selected || role.trim().length < 2) return;
              try {
                await act(
                  "/assignments",
                  {
                    blueprint_id: blueprint.id,
                    version_id: selected.id,
                    role_name: role,
                  },
                  "Penugasan berhasil dibuat.",
                );
                setDialog("");
                changeTab("assignment");
              } catch {
                /* visible error */
              }
            }}
          >
            <div className="form-fields">
              <label>
                Proyek
                <input
                  disabled
                  value={
                    workspace.projects.find((p) => p.id === project)?.name ||
                    "Laboratorium Riset"
                  }
                />
              </label>
              <label>
                Versi
                <input disabled value={`v${selected?.version_number}`} />
              </label>
              <label>
                Peran operasional
                <input
                  required
                  minLength={2}
                  maxLength={64}
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                />
              </label>
              <Notice>
                Penugasan berlaku pada proyek saat ini. Blueprint tidak
                dipindahkan antarproyek.
              </Notice>
            </div>
            <div className="dialog-footer">
              <span>Otorisasi diperiksa Core</span>
              <Button disabled={pending || role.trim().length < 2}>
                {pending ? "Menugaskan…" : "Buat penugasan"}
              </Button>
            </div>
          </form>
        ) : (
          <div>
            <div className="form-fields">
              <div className="review-version">
                <Bot size={19} />
                <strong>{blueprint.name}</strong>
                <span className="mono">v{selected?.version_number}</span>
              </div>
              {dialog === "bench" ? (
                <>
                  <ul className="scenario-preview">
                    {Object.values(scenarioNames).map((n) => (
                      <li key={n}>
                        <ShieldCheck size={15} />
                        {n}
                      </li>
                    ))}
                  </ul>
                  <Notice>
                    Instruksi sistem dan empat prompt evaluasi dikirim melalui
                    ARYN Runtime ke penyedia model jarak jauh. Model:{" "}
                    <span className="mono">{selected?.model}</span>. Tidak ada
                    fallback otomatis.
                  </Notice>
                  <label className="checkbox-field">
                    <input
                      type="checkbox"
                      checked={consent}
                      onChange={(e) => setConsent(e.target.checked)}
                    />
                    Saya menyetujui penggunaan model ini untuk evaluasi Bench.
                  </label>
                </>
              ) : dialog === "approve" ? (
                <>
                  <Notice tone="success">
                    Bench terakhir lulus {evaluation?.passed_scenarios}/
                    {evaluation?.total_scenarios} skenario.
                  </Notice>
                  <label>
                    Hash konfigurasi yang disetujui
                    <code className="hash-review wrap">
                      {selected?.payload_hash}
                    </code>
                  </label>
                  <label>
                    Catatan persetujuan
                    <textarea
                      autoFocus
                      required
                      minLength={5}
                      maxLength={2000}
                      rows={3}
                      placeholder="Alasan versi ini layak dipublikasikan…"
                      value={comments}
                      onChange={(e) => setComments(e.target.value)}
                    />
                  </label>
                </>
              ) : (
                <Notice>
                  Core memverifikasi evaluasi terakhir dan persetujuan untuk
                  hash yang tepat. Versi yang dipublikasikan tidak dapat diedit.
                </Notice>
              )}
              {pending && (
                <Busy
                  label={
                    dialog === "bench"
                      ? "Bench berjalan. Menunggu empat respons model…"
                      : "Core sedang memproses aksi…"
                  }
                />
              )}
            </div>
            <div className="dialog-footer">
              <Button
                variant="ghost"
                disabled={pending}
                onClick={() => setDialog("")}
              >
                Batal
              </Button>
              <Button
                disabled={
                  pending ||
                  (dialog === "bench" && (!consent || !modelReady)) ||
                  (dialog === "approve" && comments.trim().length < 5)
                }
                onClick={() => void runAction(dialog)}
              >
                {pending
                  ? "Memproses…"
                  : dialog === "bench"
                    ? "Mulai evaluasi"
                    : dialog === "approve"
                      ? "Setujui versi"
                      : "Publikasikan"}
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
}
